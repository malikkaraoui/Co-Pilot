"""Filtre L7 SIRET -- verifie le SIRET/SIREN via l'API recherche-entreprises gouv.fr."""

import logging
from typing import Any

import httpx

from app.errors import ExternalAPIError
from app.filters.base import BaseFilter, FilterResult

logger = logging.getLogger(__name__)

# API publique sans cle -- https://www.data.gouv.fr/dataservices/api-recherche-dentreprises
SEARCH_API_URL = "https://recherche-entreprises.api.gouv.fr/search"


class L7SiretFilter(BaseFilter):
    """Verifie le numero SIRET d'un vendeur aupres de l'API recherche-entreprises."""

    filter_id = "L7"

    def __init__(self, timeout: int = 5):
        self._timeout = timeout

    def run(self, data: dict[str, Any]) -> FilterResult:
        owner_type = (data.get("owner_type") or "").lower()
        siret = data.get("siret")

        # Particulier : pas de SIRET a verifier
        if owner_type == "private" or owner_type == "particulier":
            return self.skip("Vendeur particulier — vérification SIRET non applicable")

        # Pro sans SIRET : suspect
        if not siret and owner_type in ("pro", "professional"):
            return FilterResult(
                filter_id=self.filter_id,
                status="warning",
                score=0.3,
                message="Vendeur professionnel sans SIRET affiché",
                details={"owner_type": owner_type},
            )

        if not siret:
            return self.skip("Type de vendeur inconnu, pas de SIRET")

        # Nettoyage du SIRET
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
            response = self._call_api(cleaned)
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

        # Verification du statut
        etat = response.get("etat_administratif")
        denomination = response.get("nom_complet") or response.get("nom_raison_sociale") or ""

        if etat == "A":  # Actif
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

    def _call_api(self, siret: str) -> dict | None:
        """Appelle l'API recherche-entreprises. Retourne le premier resultat ou None."""
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(SEARCH_API_URL, params={"q": siret, "per_page": 1})
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
