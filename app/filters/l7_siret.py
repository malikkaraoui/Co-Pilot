"""Filtre L7 Entreprise -- verifie le SIRET (FR) ou UID (CH) du vendeur professionnel.

Multi-pays :
  - France : API recherche-entreprises.gouv.fr (publique, gratuite)
  - Suisse : validation format UID (CHE-xxx.xxx.xxx) + API Zefix si configuree
  - Autres : skip gracieux
"""

import logging
import os
import re
from typing import Any

import httpx

from app.errors import ExternalAPIError
from app.filters.base import VERIFIED_PRO_PLATFORMS, BaseFilter, FilterResult

logger = logging.getLogger(__name__)

# ── APIs ──────────────────────────────────────────────────────────────
# France : API publique sans cle
FR_SEARCH_API_URL = "https://recherche-entreprises.api.gouv.fr/search"

# Suisse : API Zefix (authentification requise, credentials optionnels)
CH_ZEFIX_API_URL = "https://www.zefix.admin.ch/ZefixPublicREST/api/v1/company/uid"

# ── UID Suisse : format CHE-xxx.xxx.xxx ou CHExxxxxxxxx ──────────────
UID_PATTERN = re.compile(r"^CHE[-.]?(\d{3})[-.]?(\d{3})[-.]?(\d{3})$", re.IGNORECASE)

# Poids pour le calcul du chiffre de controle UID (modulo 11)
# Source: https://www.bfs.admin.ch/bfs/fr/home/registres/registre-entreprises/uid.html
_UID_WEIGHTS = (5, 4, 3, 2, 7, 6, 5, 4)


def validate_uid_checksum(digits: str) -> bool:
    """Valide le chiffre de controle d'un UID suisse (9 chiffres).

    Le dernier chiffre est un check digit calcule en modulo 11 sur les 8 premiers.
    """
    if len(digits) != 9 or not digits.isdigit():
        return False

    total = sum(int(d) * w for d, w in zip(digits[:8], _UID_WEIGHTS))
    remainder = total % 11
    if remainder == 0:
        check = 0
    elif remainder == 1:
        return False  # UID invalide (pas de chiffre de controle possible)
    else:
        check = 11 - remainder

    return int(digits[8]) == check


def _clean_uid(raw: str) -> str | None:
    """Nettoie et extrait les 9 chiffres d'un UID brut. Retourne None si invalide."""
    m = UID_PATTERN.match(raw.strip())
    if not m:
        return None
    return m.group(1) + m.group(2) + m.group(3)


class L7SiretFilter(BaseFilter):
    """Verifie le numero d'entreprise d'un vendeur pro (SIRET en France, UID en Suisse)."""

    filter_id = "L7"

    def __init__(self, timeout: int = 5):
        self._timeout = timeout

    def run(self, data: dict[str, Any]) -> FilterResult:
        owner_type = (data.get("owner_type") or "").lower()
        country = (data.get("country") or "FR").upper()
        siret = data.get("siret")

        # Particulier : pas de verification entreprise
        if owner_type in ("private", "particulier"):
            return self.skip("Vendeur particulier — vérification entreprise non applicable")

        # Pro sans identifiant : depends de la source
        source = (data.get("source") or "").lower()
        dealer_rating = data.get("dealer_rating")
        dealer_review_count = data.get("dealer_review_count")
        if not siret and owner_type in ("pro", "professional"):
            # Plateformes verifiees : AS24 verifie le statut pro des vendeurs.
            # Si la plateforme dit "pro", c'est booleeen = pass.
            # La note vendeur enrichit le message mais ne change pas le verdict.
            if source in VERIFIED_PRO_PLATFORMS:
                msg = "Vendeur professionnel vérifié par la plateforme"
                if dealer_rating is not None and dealer_review_count is not None:
                    msg += f" — noté {dealer_rating}/5 ({dealer_review_count} avis)"
                return FilterResult(
                    filter_id=self.filter_id,
                    status="pass",
                    score=1.0,
                    message=msg,
                    details={
                        "owner_type": owner_type,
                        "country": country,
                        "source": source,
                        "platform_verified": True,
                        "dealer_rating": dealer_rating,
                        "dealer_review_count": dealer_review_count,
                    },
                )

            # Hors plateforme verifiee : dealer rating peut compenser
            has_strong_rating = (
                dealer_rating is not None
                and dealer_review_count is not None
                and float(dealer_rating) >= 4.0
                and int(dealer_review_count) >= 20
            )
            if has_strong_rating:
                return FilterResult(
                    filter_id=self.filter_id,
                    status="pass",
                    score=0.7,
                    message=f"Vendeur noté {dealer_rating}/5 ({dealer_review_count} avis)",
                    details={
                        "owner_type": owner_type,
                        "country": country,
                        "dealer_rating": dealer_rating,
                        "dealer_review_count": dealer_review_count,
                    },
                )
            if country == "CH":
                return FilterResult(
                    filter_id=self.filter_id,
                    status="warning",
                    score=0.3,
                    message="Vendeur professionnel sans numéro UID affiché",
                    details={"owner_type": owner_type, "country": country},
                )
            if country == "FR":
                return FilterResult(
                    filter_id=self.filter_id,
                    status="warning",
                    score=0.3,
                    message="Vendeur professionnel sans SIRET affiché",
                    details={"owner_type": owner_type, "country": country},
                )
            return FilterResult(
                filter_id=self.filter_id,
                status="warning",
                score=0.3,
                message="Vendeur professionnel sans numéro d'entreprise",
                details={"owner_type": owner_type, "country": country},
            )

        if not siret:
            return self.skip("Type de vendeur inconnu, pas de numéro d'entreprise")

        # Dispatch par pays
        if country == "CH":
            return self._verify_ch(siret)

        # France (defaut)
        return self._verify_fr(siret)

    # ── France : SIRET via API recherche-entreprises ─────────────────

    def _verify_fr(self, siret: str) -> FilterResult:
        """Verification SIRET/SIREN via l'API publique francaise."""
        cleaned = str(siret).replace(" ", "").strip()
        if not cleaned.isdigit() or len(cleaned) not in (9, 14):
            return FilterResult(
                filter_id=self.filter_id,
                status="fail",
                score=0.1,
                message="Numéro SIRET invalide (format incorrect)",
                details={"siret": siret, "cleaned": cleaned},
            )

        try:
            response = self._call_fr_api(cleaned)
        except ExternalAPIError as exc:
            logger.warning("L7: SIRET API error: %s", exc)
            return self.skip("API SIRET indisponible — vérification impossible")

        if not response:
            return FilterResult(
                filter_id=self.filter_id,
                status="fail",
                score=0.1,
                message="SIRET introuvable dans la base SIRENE",
                details={"siret": cleaned, "found": False},
            )

        etat = response.get("etat_administratif")
        denomination = response.get("nom_complet") or response.get("nom_raison_sociale") or ""

        if etat == "A":
            return FilterResult(
                filter_id=self.filter_id,
                status="pass",
                score=0.9,
                message=f"Entreprise active : {denomination}"
                if denomination
                else "Entreprise active",
                details={
                    "siret": cleaned,
                    "found": True,
                    "etat": etat,
                    "denomination": denomination,
                },
            )

        return FilterResult(
            filter_id=self.filter_id,
            status="warning",
            score=0.4,
            message=f"Entreprise radiée ou fermée ({etat})",
            details={
                "siret": cleaned,
                "found": True,
                "etat": etat,
                "denomination": denomination,
            },
        )

    def _call_fr_api(self, siret: str) -> dict | None:
        """Appelle l'API recherche-entreprises. Retourne le premier resultat ou None."""
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(FR_SEARCH_API_URL, params={"q": siret, "per_page": 1})
                resp.raise_for_status()
                data = resp.json()
                results = data.get("results") or []
                if not results:
                    return None
                return results[0]
        except httpx.TimeoutException:
            raise ExternalAPIError(f"SIRET API timeout ({self._timeout}s)")
        except httpx.ConnectError as exc:
            raise ExternalAPIError(f"SIRET API connexion refusee: {exc}")
        except httpx.HTTPStatusError as exc:
            raise ExternalAPIError(f"SIRET API HTTP {exc.response.status_code}")

    # ── Suisse : UID via format + API Zefix (optionnelle) ────────────

    def _verify_ch(self, raw_uid: str) -> FilterResult:
        """Verification UID suisse : format + checksum + API Zefix si configuree."""
        digits = _clean_uid(str(raw_uid))
        if not digits:
            return FilterResult(
                filter_id=self.filter_id,
                status="fail",
                score=0.1,
                message="Numéro UID invalide (format attendu : CHE-xxx.xxx.xxx)",
                details={"uid": raw_uid},
            )

        if not validate_uid_checksum(digits):
            return FilterResult(
                filter_id=self.filter_id,
                status="fail",
                score=0.1,
                message="Numéro UID invalide (chiffre de contrôle incorrect)",
                details={"uid": raw_uid, "digits": digits},
            )

        # Tenter verification Zefix si credentials disponibles
        zefix_user = os.environ.get("ZEFIX_USER")
        zefix_password = os.environ.get("ZEFIX_PASSWORD")
        if zefix_user and zefix_password:
            try:
                company = self._call_zefix_api(digits, zefix_user, zefix_password)
            except ExternalAPIError as exc:
                logger.warning("L7: Zefix API error: %s", exc)
                return FilterResult(
                    filter_id=self.filter_id,
                    status="pass",
                    score=0.7,
                    message="UID valide (format vérifié, API Zefix indisponible)",
                    details={"uid": raw_uid, "digits": digits, "zefix": "unavailable"},
                )

            if not company:
                return FilterResult(
                    filter_id=self.filter_id,
                    status="fail",
                    score=0.1,
                    message="UID introuvable dans le registre du commerce suisse",
                    details={"uid": raw_uid, "digits": digits, "found": False},
                )

            name = company.get("name") or ""
            status = company.get("status") or ""
            is_active = status.lower() in ("", "active", "actif")
            if is_active:
                return FilterResult(
                    filter_id=self.filter_id,
                    status="pass",
                    score=0.9,
                    message=f"Entreprise suisse active : {name}"
                    if name
                    else "Entreprise suisse active",
                    details={
                        "uid": raw_uid,
                        "digits": digits,
                        "found": True,
                        "name": name,
                        "status": status,
                    },
                )

            return FilterResult(
                filter_id=self.filter_id,
                status="warning",
                score=0.4,
                message=f"Entreprise suisse radiée ({status})",
                details={
                    "uid": raw_uid,
                    "digits": digits,
                    "found": True,
                    "name": name,
                    "status": status,
                },
            )

        # Pas de credentials Zefix : validation format seule
        formatted = f"CHE-{digits[:3]}.{digits[3:6]}.{digits[6:9]}"
        return FilterResult(
            filter_id=self.filter_id,
            status="pass",
            score=0.7,
            message=f"UID valide : {formatted} (vérification registre non configurée)",
            details={
                "uid": raw_uid,
                "digits": digits,
                "formatted": formatted,
                "zefix": "not_configured",
            },
        )

    def _call_zefix_api(self, digits: str, user: str, password: str) -> dict | None:
        """Appelle l'API Zefix pour verifier un UID. Retourne le resultat ou None."""
        uid_str = f"CHE{digits}"
        url = f"{CH_ZEFIX_API_URL}/{uid_str}"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(url, auth=(user, password))
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list):
                    return data[0] if data else None
                return data
        except httpx.TimeoutException:
            raise ExternalAPIError(f"Zefix API timeout ({self._timeout}s)")
        except httpx.ConnectError as exc:
            raise ExternalAPIError(f"Zefix API connexion refusee: {exc}")
        except httpx.HTTPStatusError as exc:
            raise ExternalAPIError(f"Zefix API HTTP {exc.response.status_code}")
