"""Filtre L6 Telephone -- analyse le numero de telephone pour detecter des schemas suspects.

Multi-pays : adapte la validation selon le pays (FR, CH, DE, etc.)
detecte via ad_data["country"] injecte par routes.py.

Detecte :
- Les indicatifs etrangers (ex: +49 sur une annonce francaise)
- Les prefixes ARCEP reserves au demarchage telephonique (France)
- Les numeros virtuels OnOff (identite masquee)
- L'absence de telephone (red flag, surtout pour un pro)

Le telephone est un signal fort : un vendeur qui donne son vrai numero
est plus credible qu'un vendeur qui se cache derriere la messagerie.
"""

import logging
import re
from typing import Any

from app.filters.base import BaseFilter, FilterResult
from app.filters.phone_prefixes import (
    PHONE_DIAL_TABLE,
    detect_phone_prefix_country,
    get_country_flag,
    get_country_name,
    get_country_prefixes,
    is_local_prefix,
)

logger = logging.getLogger(__name__)

# ── Patterns par pays ────────────────────────────────────────────────
# Regex strictes pour valider le format des numeros connus.
# Si le numero ne matche aucun pattern, on ne penalise pas (score 0.8)
# car nos regex ne couvrent pas tous les cas (formats exotiques, numeros courts...)

# France : 06/07 = mobile, 01-05/09 = fixe
FR_MOBILE_PATTERN = re.compile(r"^(?:\+33|0033|0)[67]\d{8}$")
FR_LANDLINE_PATTERN = re.compile(r"^(?:\+33|0033|0)[1-59]\d{8}$")

# Suisse : 075-079 = mobile, 02-06 = fixe
CH_MOBILE_PATTERN = re.compile(r"^(?:\+41|0041|0)7[5-9]\d{7}$")
CH_LANDLINE_PATTERN = re.compile(r"^(?:\+41|0041|0)[2-6]\d{8}$")

# Allemagne : 015x-017x = mobile, 02-09 = fixe (longueur variable)
DE_MOBILE_PATTERN = re.compile(r"^(?:\+49|0049|0)1[5-7]\d{8,9}$")
DE_LANDLINE_PATTERN = re.compile(r"^(?:\+49|0049|0)[2-9]\d{6,10}$")

# Indicatifs par pays, pre-calcules au chargement du module
COUNTRY_PREFIXES: dict[str, tuple[str, ...]] = {
    c: get_country_prefixes(c) for c in PHONE_DIAL_TABLE
}

# Prefixes ARCEP reserves au demarchage telephonique (France, depuis 1er janvier 2023)
# Un vendeur qui utilise ces numeros n'est probablement pas un vrai vendeur de voiture.
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
# Ces numeros permettent d'avoir un second numero jetable.
# Pas forcement malveillant, mais l'identite du vendeur est masquee.
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
    return is_local_prefix(cleaned, country)


class L6PhoneFilter(BaseFilter):
    """Analyse le numero de telephone du vendeur pour detecter des indicatifs etrangers ou formats suspects.

    Logique en 3 etapes :
    1. Pas de telephone ? -> warning/fail selon le contexte
    2. Indicatif etranger ? -> warning (recoupement avec L8 import)
    3. Validation par pays (FR/CH/DE) ou generique
    """

    filter_id = "L6"

    def run(self, data: dict[str, Any]) -> FilterResult:
        phone = data.get("phone")
        country = (data.get("country") or "FR").upper()
        owner_type = (data.get("owner_type") or "").lower()

        if not phone:
            # La Centrale ne fournit pas le telephone dans les donnees structurees.
            # Le vendeur est contactable via la messagerie du site.
            source = (data.get("source") or "").lower()
            if source == "lacentrale":
                return self.neutral(
                    "La Centrale ne fournit pas le téléphone — contact via messagerie du site"
                )
            # LBC cache le tel derriere "Voir le numero" (API authentifiee)
            # Le numero existe, on ne peut juste pas le verifier sans connexion
            if data.get("has_phone"):
                return self.neutral(
                    "Connectez-vous sur LeBonCoin pour révéler et vérifier le numéro"
                )
            # Aucun numero : red flag quel que soit le type de vendeur
            if owner_type in ("private", "particulier", ""):
                return FilterResult(
                    filter_id=self.filter_id,
                    status="warning",
                    score=0.2,
                    message="Aucun numéro de téléphone — inhabituel même pour un particulier",
                    details={"owner_type": owner_type or "private", "no_phone": True},
                )
            # Pro sans telephone : encore plus louche
            return FilterResult(
                filter_id=self.filter_id,
                status="fail",
                score=0.0,
                message="Vendeur pro sans numéro de téléphone — très suspect",
                details={"owner_type": owner_type, "no_phone_pro": True},
            )

        # Normalisation : espaces, tirets, points + prefixe de tronc (0) (DE/AT/CH)
        cleaned = re.sub(r"[\s\-.]", "", phone.strip())
        cleaned = cleaned.replace("(0)", "")  # "+49(0)271" -> "+49271"
        cleaned = re.sub(r"[()]", "", cleaned)  # parentheses restantes

        # Verification d'indicatif basee sur la table connue (pas de regex gloutonne +437)
        # Longest-prefix match pour eviter les ambiguites (+43 vs +437)
        prefix_country, canonical_prefix = detect_phone_prefix_country(cleaned)
        if prefix_country and canonical_prefix and prefix_country != country:
            prefix_country_name = get_country_name(prefix_country)
            prefix_country_flag = get_country_flag(prefix_country)
            logger.info(
                "L6: foreign prefix detected: %s -> %s (ad_country=%s)",
                canonical_prefix,
                prefix_country,
                country,
            )
            return FilterResult(
                filter_id=self.filter_id,
                status="warning",
                score=0.3,
                message=(
                    f"Numéro avec indicatif étranger "
                    f"({canonical_prefix} {prefix_country_flag} {prefix_country_name})"
                ).strip(),
                details={
                    "phone": phone,
                    "prefix": canonical_prefix,
                    "prefix_country": prefix_country,
                    "prefix_country_name": prefix_country_name,
                    "prefix_country_flag": prefix_country_flag,
                    "is_foreign": True,
                    "country": country,
                },
            )

        # ── Dispatch par pays pour les checks specifiques ─────────────
        if country == "FR":
            return self._check_fr(cleaned, phone)

        if country == "CH":
            return self._check_ch(cleaned, phone)

        if country == "DE":
            return self._check_de(cleaned, phone)

        # Autres pays : validation basique (indicatif local connu ou pas)
        return self._check_generic(cleaned, phone, country)

    def _check_fr(self, cleaned: str, phone: str) -> FilterResult:
        """Validation specifique France.

        Verifie dans l'ordre :
        1. Prefixes de demarchage ARCEP (fail immediat)
        2. Numeros virtuels OnOff (warning)
        3. Format mobile/fixe standard (pass)
        4. Format non reconnu mais numero present (pass attenue)
        """
        # Normaliser vers format 0XXXXXXXXX pour le matching
        local = cleaned
        if local.startswith("+33"):
            local = "0" + local[3:]
        elif local.startswith("0033"):
            local = "0" + local[4:]

        # Prefixes ARCEP de demarchage = red flag fort
        if any(local.startswith(p) for p in TELEMARKETING_PREFIXES):
            logger.info("L6: telemarketing prefix detected: %s", local[:4])
            return FilterResult(
                filter_id=self.filter_id,
                status="fail",
                score=0.1,
                message="Numéro de démarchage téléphonique (préfixe ARCEP réservé)",
                details={"phone": phone, "type": "telemarketing_arcep", "prefix": local[:4]},
            )

        # Numeros virtuels OnOff = identite potentiellement masquee
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
            message="Numéro présent (format non vérifié strictement)",
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
            message="Numéro présent (format non vérifié strictement)",
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
            message="Numéro présent (format non vérifié strictement)",
            details={"phone": phone, "type": "present_unverified"},
        )

    def _check_generic(self, cleaned: str, phone: str, country: str) -> FilterResult:
        """Validation generique pour les pays non-specifiques.

        On fait le minimum : verifier si l'indicatif est local.
        Pas de validation de format car on ne connait pas les regles de chaque pays.
        """
        # Si le numero commence par un indicatif local connu, c'est OK
        if _is_local_prefix(cleaned, country):
            return FilterResult(
                filter_id=self.filter_id,
                status="pass",
                score=0.8,
                message=f"Numéro local ({country}) — format non vérifié strictement",
                details={"phone": phone, "type": f"local_{country.lower()}"},
            )

        # Numero sans indicatif (local) : probablement OK
        if not cleaned.startswith("+"):
            return FilterResult(
                filter_id=self.filter_id,
                status="pass",
                score=0.7,
                message="Numéro local (format non vérifié strictement)",
                details={"phone": phone, "type": "local_generic"},
            )

        logger.info("L6: phone present, format non-standard (%s): %s", country, phone)
        return FilterResult(
            filter_id=self.filter_id,
            status="pass",
            score=0.8,
            message="Numéro présent (format non vérifié strictement)",
            details={"phone": phone, "type": "present_unverified"},
        )
