"""Filtre L1 Qualite d'Extraction -- valide la completude des donnees extraites."""

import logging
from typing import Any

from app.filters.base import BaseFilter, FilterResult

logger = logging.getLogger(__name__)

CRITICAL_FIELDS = ["price_eur", "make", "model", "year_model", "mileage_km"]
SECONDARY_FIELDS = ["fuel", "gearbox", "phone", "color", "location"]


class L1ExtractionFilter(BaseFilter):
    """Verifie que les donnees extraites de l'annonce contiennent les champs critiques et valides."""

    filter_id = "L1"

    def run(self, data: dict[str, Any]) -> FilterResult:
        missing_critical = []
        missing_secondary = []

        for field in CRITICAL_FIELDS:
            if not data.get(field):
                missing_critical.append(field)

        for field in SECONDARY_FIELDS:
            val = data.get(field)
            if not val:
                missing_secondary.append(field)

        total_fields = len(CRITICAL_FIELDS) + len(SECONDARY_FIELDS)
        present = total_fields - len(missing_critical) - len(missing_secondary)
        score = present / total_fields

        if missing_critical:
            status = "fail" if len(missing_critical) >= 3 else "warning"
            message = f"Donnees incompletes : {', '.join(missing_critical)} manquant(s)"
        elif missing_secondary:
            status = "warning"
            message = f"Quelques infos secondaires manquantes ({len(missing_secondary)})"
        else:
            status = "pass"
            message = "Toutes les donnees de l'annonce sont presentes"

        logger.info("L1: %s (critical_missing=%d, secondary_missing=%d)",
                     status, len(missing_critical), len(missing_secondary))

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
