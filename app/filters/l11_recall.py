"""Filtre L11 Rappel Constructeur -- verifie si le vehicule est concerne par un rappel officiel.

Les rappels constructeur sont des defauts de fabrication identifies apres la mise en
circulation. C'est un signal fort : un rappel non traite peut impacter la securite
(freinage, airbag, direction...) et la valeur de revente.

Les donnees proviennent de la table manufacturer_recalls, alimentee par les seeds.
Si la table n'existe pas encore (migration pas jouee), le filtre se desactive sans crasher.
"""

import logging
from typing import Any

from sqlalchemy.exc import OperationalError

from app.filters.base import BaseFilter, FilterResult

logger = logging.getLogger(__name__)

# Bornes de validation pour eviter les annees absurdes (typo, parsing foireux)
MIN_YEAR = 1900
MAX_YEAR = 2100


def _find_recalls(make: str, model: str, year: int) -> list[dict[str, Any]]:
    """Recherche les rappels constructeur pour un vehicule donne.

    Args:
        make: Marque du vehicule.
        model: Modele du vehicule.
        year: Annee de production.

    Returns:
        Liste de dicts avec recall_type, description, gov_url, severity.
    """
    from app.models.manufacturer_recall import ManufacturerRecall
    from app.services.vehicle_lookup import find_vehicle

    vehicle = find_vehicle(make, model)
    if not vehicle:
        return []

    # Filtre par plage d'annees de production : un rappel concerne les vehicules
    # fabriques entre year_start et year_end (pas l'annee de l'annonce)
    try:
        recalls = ManufacturerRecall.query.filter(
            ManufacturerRecall.vehicle_id == vehicle.id,
            ManufacturerRecall.year_start <= year,
            ManufacturerRecall.year_end >= year,
        ).all()
    except OperationalError:
        # Table pas encore creee (migration pas jouee) : on skip sans crasher
        logger.warning("Table manufacturer_recalls absente — filtre L11 desactive")
        return []

    return [
        {
            "recall_type": r.recall_type,
            "description": r.description,
            "gov_url": r.gov_url,
            "severity": r.severity,
        }
        for r in recalls
    ]


class L11RecallFilter(BaseFilter):
    """Verifie si le vehicule est concerne par un rappel constructeur officiel."""

    filter_id = "L11"

    def run(self, data: dict[str, Any]) -> FilterResult:
        """Recherche les rappels constructeur connus pour le vehicule de l'annonce.

        Score binaire : 1.0 si aucun rappel, 0.0 si au moins un rappel concerne.
        Le message inclut la description du rappel le plus pertinent.
        """
        # Tolere les deux noms de champ (make vs brand, year vs year_model)
        # selon la source de donnees (extraction vs API interne)
        make = data.get("make") or data.get("brand")
        model = data.get("model")
        year = data.get("year") or data.get("year_model")

        if not make or not model or not year:
            return self.neutral("Données insuffisantes pour vérifier les rappels")

        try:
            year = int(year)
        except (ValueError, TypeError):
            return self.neutral("Annee invalide")

        if not (MIN_YEAR <= year <= MAX_YEAR):
            return self.neutral("Annee hors plage valide")

        recalls = _find_recalls(make, model, year)

        # Pas de rappel = bon signe, score max
        if not recalls:
            return FilterResult(
                filter_id=self.filter_id,
                status="pass",
                score=1.0,
                message="Aucun rappel constructeur connu pour ce véhicule",
                details=None,
            )

        # On affiche le premier rappel dans le message principal.
        # Tous les rappels sont dans details.recalls pour la vue detaillee.
        recall = recalls[0]
        return FilterResult(
            filter_id=self.filter_id,
            status="fail",
            score=0.0,
            message=f"Véhicule concerné par le rappel {recall['description']}",
            details={
                "recall_type": recall["recall_type"],
                "description": recall["description"],
                "gov_url": recall["gov_url"],
                "severity": recall["severity"],
                "recall_count": len(recalls),
                "recalls": recalls,
            },
        )
