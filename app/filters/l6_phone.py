"""Filtre L6 Telephone -- analyse le numero de telephone pour detecter des schemas suspects.

Multi-pays : adapte la validation selon le pays (FR, CH, DE, etc.)
detecte via ad_data["country"] injecte par routes.py.
"""

import logging
import re
from typing import Any

from app.filters.base import BaseFilter, FilterResult

logger = logging.getLogger(__name__)

# ── Patterns par pays ────────────────────────────────────────────────
# France
FR_MOBILE_PATTERN = re.compile(r"^(?:\+33|0033|0)[67]\d{8}$")
FR_LANDLINE_PATTERN = re.compile(r"^(?:\+33|0033|0)[1-59]\d{8}$")

# Suisse
CH_MOBILE_PATTERN = re.compile(r"^(?:\+41|0041|0)7[5-9]\d{7}$")
CH_LANDLINE_PATTERN = re.compile(r"^(?:\+41|0041|0)[2-6]\d{8}$")

# Allemagne
DE_MOBILE_PATTERN = re.compile(r"^(?:\+49|0049|0)1[5-7]\d{8,9}$")
DE_LANDLINE_PATTERN = re.compile(r"^(?:\+49|0049|0)[2-9]\d{6,10}$")

# Indicatifs locaux par pays
COUNTRY_PREFIXES: dict[str, tuple[str, ...]] = {
    "FR": ("+33", "0033"),
    "CH": ("+41", "0041"),
    "DE": ("+49", "0049"),
    "AT": ("+43", "0043"),
    "IT": ("+39", "0039"),
    "NL": ("+31", "0031"),
    "BE": ("+32", "0032"),
    "ES": ("+34", "0034"),
}

# Prefixes ARCEP reserves au demarchage telephonique (France, depuis 1er janvier 2023)
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

# Numeros virtuels OnOff (France)
VIRTUAL_PREFIXES = (
    "064466",
    "064467",
    "064468",
    "064469",
    "07568",
    "07569",
)


def _is_local_prefix(cleaned: str, country: str) -> bool:
    """Verifie si le numero commence par un indicatif local du pays."""
    prefixes = COUNTRY_PREFIXES.get(country, ())
    return any(cleaned.startswith(p) for p in prefixes)


class L6PhoneFilter(BaseFilter):
    """Analyse le numero de telephone du vendeur pour detecter des indicatifs etrangers ou formats suspects."""

    filter_id = "L6"

    def run(self, data: dict[str, Any]) -> FilterResult:
        phone = data.get("phone")
        country = (data.get("country") or "FR").upper()
        owner_type = (data.get("owner_type") or "").lower()

        if not phone:
            # LBC cache le tel derriere "Voir le numero" (API authentifiee)
            if data.get("has_phone"):
                return FilterResult(
                    filter_id=self.filter_id,
                    status="skip",
                    score=0.0,
                    message="Connectez-vous sur LeBonCoin pour révéler le numéro",
                    details={"phone_login_hint": True},
                )
            # Particulier sans telephone : normal, pas de penalite
            if owner_type in ("private", "particulier", ""):
                return self.skip("Pas de numéro — vendeur particulier, pas de pénalité")
            # Pro sans telephone : zero confiance
            return FilterResult(
                filter_id=self.filter_id,
                status="fail",
                score=0.0,
                message="Vendeur professionnel sans numéro de téléphone",
                details={"owner_type": owner_type, "no_phone_pro": True},
            )

        # Normalisation : suppression des espaces, tirets, points
        cleaned = re.sub(r"[\s\-.]", "", phone.strip())

        # Verification d'indicatif : un +XX non-local est etranger
        foreign_match = re.match(r"^\+(\d{1,3})", cleaned)
        if foreign_match:
            # Si le prefix correspond au pays de l'annonce, c'est local
            if _is_local_prefix(cleaned, country):
                pass  # continue vers la validation locale
            else:
                prefix = "+" + foreign_match.group(1)
                logger.info("L6: foreign prefix detected: %s (country=%s)", prefix, country)
                return FilterResult(
                    filter_id=self.filter_id,
                    status="warning",
                    score=0.3,
                    message=f"Numéro avec indicatif étranger ({prefix})",
                    details={
                        "phone": phone,
                        "prefix": prefix,
                        "is_foreign": True,
                        "country": country,
                    },
                )

        # ── France : checks specifiques ──────────────────────────────
        if country == "FR":
            return self._check_fr(cleaned, phone)

        # ── Suisse ───────────────────────────────────────────────────
        if country == "CH":
            return self._check_ch(cleaned, phone)

        # ── Allemagne ────────────────────────────────────────────────
        if country == "DE":
            return self._check_de(cleaned, phone)

        # ── Autres pays : validation basique ─────────────────────────
        return self._check_generic(cleaned, phone, country)

    def _check_fr(self, cleaned: str, phone: str) -> FilterResult:
        """Validation specifique France."""
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
                message="Numéro de démarchage téléphonique (préfixe ARCEP réservé)",
                details={"phone": phone, "type": "telemarketing_arcep", "prefix": local[:4]},
            )

        if any(local.startswith(p) for p in VIRTUAL_PREFIXES):
            logger.info("L6: virtual number detected: %s", local[:6])
            return FilterResult(
                filter_id=self.filter_id,
                status="warning",
                score=0.3,
                message="Numéro virtuel (identité potentiellement masquée)",
                details={"phone": phone, "type": "virtual_onoff", "prefix": local[:6]},
            )

        if FR_MOBILE_PATTERN.match(cleaned):
            return FilterResult(
                filter_id=self.filter_id,
                status="pass",
                score=1.0,
                message="Numéro de mobile français standard",
                details={"phone": phone, "type": "mobile_fr"},
            )

        if FR_LANDLINE_PATTERN.match(cleaned):
            return FilterResult(
                filter_id=self.filter_id,
                status="pass",
                score=1.0,
                message="Numéro de fixe français",
                details={"phone": phone, "type": "landline_fr"},
            )

        # Le telephone est present mais ne matche aucun pattern connu.
        # C'est une limitation de nos regex, pas un signal suspect.
        # Un vendeur qui donne son numero = bon signe.
        logger.info("L6: phone present, format non-standard (FR): %s", phone)
        return FilterResult(
            filter_id=self.filter_id,
            status="pass",
            score=0.8,
            message="Numéro de téléphone présent",
            details={"phone": phone, "type": "present_unverified"},
        )

    def _check_ch(self, cleaned: str, phone: str) -> FilterResult:
        """Validation specifique Suisse."""
        if CH_MOBILE_PATTERN.match(cleaned):
            return FilterResult(
                filter_id=self.filter_id,
                status="pass",
                score=1.0,
                message="Numéro de mobile suisse standard",
                details={"phone": phone, "type": "mobile_ch"},
            )

        if CH_LANDLINE_PATTERN.match(cleaned):
            return FilterResult(
                filter_id=self.filter_id,
                status="pass",
                score=1.0,
                message="Numéro de fixe suisse",
                details={"phone": phone, "type": "landline_ch"},
            )

        logger.info("L6: phone present, format non-standard (CH): %s", phone)
        return FilterResult(
            filter_id=self.filter_id,
            status="pass",
            score=0.8,
            message="Numéro de téléphone présent",
            details={"phone": phone, "type": "present_unverified"},
        )

    def _check_de(self, cleaned: str, phone: str) -> FilterResult:
        """Validation specifique Allemagne."""
        if DE_MOBILE_PATTERN.match(cleaned):
            return FilterResult(
                filter_id=self.filter_id,
                status="pass",
                score=1.0,
                message="Numéro de mobile allemand standard",
                details={"phone": phone, "type": "mobile_de"},
            )

        if DE_LANDLINE_PATTERN.match(cleaned):
            return FilterResult(
                filter_id=self.filter_id,
                status="pass",
                score=1.0,
                message="Numéro de fixe allemand",
                details={"phone": phone, "type": "landline_de"},
            )

        logger.info("L6: phone present, format non-standard (DE): %s", phone)
        return FilterResult(
            filter_id=self.filter_id,
            status="pass",
            score=0.8,
            message="Numéro de téléphone présent",
            details={"phone": phone, "type": "present_unverified"},
        )

    def _check_generic(self, cleaned: str, phone: str, country: str) -> FilterResult:
        """Validation generique pour les pays non-specifiques."""
        # Si le numero commence par un indicatif local connu, c'est OK
        if _is_local_prefix(cleaned, country):
            return FilterResult(
                filter_id=self.filter_id,
                status="pass",
                score=0.8,
                message=f"Numéro avec indicatif local ({country})",
                details={"phone": phone, "type": f"local_{country.lower()}"},
            )

        # Numero sans indicatif (local) : probablement OK
        if not cleaned.startswith("+"):
            return FilterResult(
                filter_id=self.filter_id,
                status="pass",
                score=0.7,
                message="Numéro local",
                details={"phone": phone, "type": "local_generic"},
            )

        logger.info("L6: phone present, format non-standard (%s): %s", country, phone)
        return FilterResult(
            filter_id=self.filter_id,
            status="pass",
            score=0.8,
            message="Numéro de téléphone présent",
            details={"phone": phone, "type": "present_unverified"},
        )
