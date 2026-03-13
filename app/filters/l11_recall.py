"""Filtre L11 Rappel Constructeur -- verifie si le vehicule est concerne par un rappel officiel."""

import logging
from typing import Any

from app.filters.base import BaseFilter, FilterResult

logger = logging.getLogger(__name__)


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

    recalls = ManufacturerRecall.query.filter(
        ManufacturerRecall.vehicle_id == vehicle.id,
        ManufacturerRecall.year_start <= year,
        ManufacturerRecall.year_end >= year,
    ).all()

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
        make = data.get("make") or data.get("brand")
        model = data.get("model")
        year = data.get("year")

        if not make or not model or not year:
            return self.neutral("Donnees insuffisantes pour verifier les rappels")

        try:
            year = int(year)
        except (ValueError, TypeError):
            return self.neutral("Annee invalide")

        recalls = _find_recalls(make, model, year)

        if not recalls:
            return FilterResult(
                filter_id=self.filter_id,
                status="pass",
                score=1.0,
                message="Aucun rappel constructeur connu pour ce vehicule",
                details=None,
            )

        # Construire le message avec tous les rappels trouves
        recall = recalls[0]  # Le plus pertinent
        return FilterResult(
            filter_id=self.filter_id,
            status="fail",
            score=0.0,
            message=f"Vehicule concerne par le rappel {recall['description']}",
            details={
                "recall_type": recall["recall_type"],
                "description": recall["description"],
                "gov_url": recall["gov_url"],
                "severity": recall["severity"],
                "recall_count": len(recalls),
                "recalls": recalls,
            },
        )
