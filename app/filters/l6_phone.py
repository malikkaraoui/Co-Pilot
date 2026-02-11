"""Filtre L6 Telephone -- analyse le numero de telephone pour detecter des schemas suspects."""

import logging
import re
from typing import Any

from app.filters.base import BaseFilter, FilterResult

logger = logging.getLogger(__name__)

# Prefixes mobiles francais
FR_MOBILE_PATTERN = re.compile(r"^(?:\+33|0033|0)[67]\d{8}$")
FR_LANDLINE_PATTERN = re.compile(r"^(?:\+33|0033|0)[1-59]\d{8}$")
FOREIGN_PREFIX_PATTERN = re.compile(r"^\+(?!33)\d{1,3}")


class L6PhoneFilter(BaseFilter):
    """Analyse le numero de telephone du vendeur pour detecter des indicatifs etrangers ou formats suspects."""

    filter_id = "L6"

    def run(self, data: dict[str, Any]) -> FilterResult:
        phone = data.get("phone")

        if not phone:
            return self.skip("Pas de numero de telephone dans l'annonce")

        # Normalisation : suppression des espaces, tirets, points
        cleaned = re.sub(r"[\s\-.]", "", phone.strip())

        # Verification d'indicatif etranger
        foreign_match = FOREIGN_PREFIX_PATTERN.search(cleaned)
        if foreign_match:
            prefix = foreign_match.group()
            logger.info("L6: foreign prefix detected: %s", prefix)
            return FilterResult(
                filter_id=self.filter_id,
                status="warning",
                score=0.3,
                message=f"Numero avec indicatif etranger ({prefix})",
                details={
                    "phone": phone,
                    "prefix": prefix,
                    "is_foreign": True,
                },
            )

        # Verification mobile francais
        if FR_MOBILE_PATTERN.match(cleaned):
            return FilterResult(
                filter_id=self.filter_id,
                status="pass",
                score=1.0,
                message="Numero de mobile francais standard",
                details={"phone": phone, "type": "mobile_fr"},
            )

        # Verification fixe francais
        if FR_LANDLINE_PATTERN.match(cleaned):
            return FilterResult(
                filter_id=self.filter_id,
                status="pass",
                score=0.9,
                message="Numero de fixe francais",
                details={"phone": phone, "type": "landline_fr"},
            )

        # Format suspect
        logger.info("L6: suspect phone format: %s", phone)
        return FilterResult(
            filter_id=self.filter_id,
            status="warning",
            score=0.4,
            message="Format de numero suspect",
            details={"phone": phone, "type": "unknown"},
        )
