"""Filtre L1 Qualite d'Extraction -- valide la completude des donnees extraites.

Premier filtre de la chaine : verifie que l'extension a bien reussi a extraire
les donnees structurees de l'annonce. Si les champs critiques manquent (prix,
marque, modele...), les filtres suivants ne pourront pas travailler correctement.
"""

import logging
from typing import Any

from app.filters.base import BaseFilter, FilterResult

logger = logging.getLogger(__name__)

# Champs sans lesquels l'analyse perd tout son sens.
# Si price/make/model manquent, on ne peut meme pas comparer au marche.
CRITICAL_FIELDS = ["price_eur", "make", "model", "year_model", "mileage_km"]

# Champs utiles mais pas bloquants. Leur absence degrade le score
# mais n'empeche pas les autres filtres de tourner.
SECONDARY_FIELDS = ["fuel", "gearbox", "phone", "color", "location"]


class L1ExtractionFilter(BaseFilter):
    """Verifie que les donnees extraites de l'annonce contiennent les champs critiques et valides."""

    filter_id = "L1"

    def run(self, data: dict[str, Any]) -> FilterResult:
        """Verifie la completude des donnees extraites par l'extension.

        Le score est proportionnel au nombre de champs presents.
        Les champs critiques manquants degradent plus fortement le verdict
        que les champs secondaires.
        """
        missing_critical = []
        missing_secondary = []

        for field in CRITICAL_FIELDS:
            if data.get(field) is None:
                missing_critical.append(field)

        for field in SECONDARY_FIELDS:
            if data.get(field) is None:
                # phone est cache derriere "Voir le numero" sur LBC ;
                # has_phone=True signifie qu'il existe mais n'est pas revele.
                if field == "phone" and data.get("has_phone"):
                    continue
                missing_secondary.append(field)

        # Score = ratio champs presents / total. Simple et lineaire.
        total_fields = len(CRITICAL_FIELDS) + len(SECONDARY_FIELDS)
        present = total_fields - len(missing_critical) - len(missing_secondary)
        score = present / total_fields

        # >=3 champs critiques manquants = fail (annonce quasi-inutilisable)
        # Sinon warning si des champs critiques manquent
        if missing_critical:
            status = "fail" if len(missing_critical) >= 3 else "warning"
            message = f"Données incomplètes : {', '.join(missing_critical)} manquant(s)"
        elif missing_secondary:
            status = "warning"
            message = f"Quelques infos secondaires manquantes ({len(missing_secondary)})"
        else:
            status = "pass"
            message = "Toutes les données de l'annonce sont présentes"

        logger.info(
            "L1: %s (critical_missing=%d, secondary_missing=%d)",
            status,
            len(missing_critical),
            len(missing_secondary),
        )

        return FilterResult(
            filter_id=self.filter_id,
            status=status,
            score=score,
            message=message,
            details={
                "missing_critical": missing_critical,
                "missing_secondary": missing_secondary,
                "fields_present": present,
                "fields_total": total_fields,
            },
        )
