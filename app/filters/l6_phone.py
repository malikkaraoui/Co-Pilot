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

# Prefixes ARCEP reserves au demarchage telephonique (depuis 1er janvier 2023)
# Source: plan de numerotation ARCEP, liste officielle
TELEMARKETING_PREFIXES = (
    "0162",
    "0163",  # Ile-de-France
    "0270",
    "0271",  # Nord-Ouest
    "0377",
    "0378",  # Nord-Est
    "0424",
    "0425",  # Sud-Est
    "0568",
    "0569",  # Sud-Ouest
    "0948",
    "0949",  # Numeros non geographiques
    "09475",
    "09476",
    "09477",
    "09478",
    "09479",  # Outre-mer
)

# Numeros virtuels OnOff (souvent utilises pour masquer l'identite)
VIRTUAL_PREFIXES = (
    "064466",
    "064467",
    "064468",
    "064469",
    "07568",
    "07569",
)


class L6PhoneFilter(BaseFilter):
    """Analyse le numero de telephone du vendeur pour detecter des indicatifs etrangers ou formats suspects."""

    filter_id = "L6"

    def run(self, data: dict[str, Any]) -> FilterResult:
        phone = data.get("phone")

        if not phone:
            # LBC cache le tel derriere "Voir le numero" (API authentifiee)
            if data.get("has_phone"):
                return FilterResult(
                    filter_id=self.filter_id,
                    status="skip",
                    score=0.0,
                    message="Connectez-vous sur LeBonCoin pour reveler le numero",
                    details={"phone_login_hint": True},
                )
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

        # Detection prefixes demarchage ARCEP
        # Normaliser vers format 0XXXXXXXXX pour le matching
        local = cleaned
        if local.startswith("+33"):
            local = "0" + local[3:]
        elif local.startswith("0033"):
            local = "0" + local[4:]

        if any(local.startswith(p) for p in TELEMARKETING_PREFIXES):
            logger.info("L6: telemarketing prefix detected: %s", local[:4])
            return FilterResult(
                filter_id=self.filter_id,
                status="fail",
                score=0.1,
                message="Numero de demarchage telephonique (prefixe ARCEP reserve)",
                details={"phone": phone, "type": "telemarketing_arcep", "prefix": local[:4]},
            )

        # Detection numeros virtuels (OnOff)
        if any(local.startswith(p) for p in VIRTUAL_PREFIXES):
            logger.info("L6: virtual number detected: %s", local[:6])
            return FilterResult(
                filter_id=self.filter_id,
                status="warning",
                score=0.3,
                message="Numero virtuel (identite potentiellement masquee)",
                details={"phone": phone, "type": "virtual_onoff", "prefix": local[:6]},
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
