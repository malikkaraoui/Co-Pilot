"""Filtre L7 SIRET -- verifie le SIRET/SIREN via l'API publique gouv.fr."""

import logging
from typing import Any

import httpx

from app.errors import ExternalAPIError
from app.filters.base import BaseFilter, FilterResult

logger = logging.getLogger(__name__)

SIRET_API_URL = "https://entreprise.data.gouv.fr/api/sirene/v3/etablissements"


class L7SiretFilter(BaseFilter):
    """Verifie le numero SIRET d'un vendeur aupres de l'API publique gouv.fr."""

    filter_id = "L7"

    def __init__(self, timeout: int = 5):
        self._timeout = timeout

    def run(self, data: dict[str, Any]) -> FilterResult:
        siret = data.get("siret")

        if not siret:
            return self.skip("Pas de numero SIRET dans l'annonce")

        # Nettoyage du SIRET
        cleaned = str(siret).replace(" ", "").strip()
        if not cleaned.isdigit() or len(cleaned) not in (9, 14):
            return FilterResult(
                filter_id=self.filter_id,
                status="fail",
                score=0.1,
                message="Numero SIRET invalide (format incorrect)",
                details={"siret": siret, "cleaned": cleaned},
            )

        try:
            response = self._call_api(cleaned)
        except ExternalAPIError as exc:
            logger.warning("L7: SIRET API error: %s", exc)
            return self.skip("API SIRET indisponible -- verification impossible")

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
        denomination = response.get("unite_legale", {}).get("denomination") or ""

        if etat == "A":  # Actif
            return FilterResult(
                filter_id=self.filter_id,
                status="pass",
                score=0.9,
                message=f"Entreprise active : {denomination}" if denomination else "Entreprise active",
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
            message=f"Entreprise radiee ou fermee ({etat})",
            details={
                "siret": cleaned,
                "found": True,
                "etat": etat,
                "denomination": denomination,
            },
        )

    def _call_api(self, siret: str) -> dict | None:
        """Appelle l'API SIRET. Retourne le dict de l'etablissement ou None."""
        try:
            with httpx.Client(timeout=self._timeout) as client:
                url = f"{SIRET_API_URL}/{siret}"
                resp = client.get(url)
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                data = resp.json()
                return data.get("etablissement")
        except httpx.TimeoutException:
            raise ExternalAPIError(f"SIRET API timeout ({self._timeout}s)")
        except httpx.HTTPStatusError as exc:
            raise ExternalAPIError(f"SIRET API HTTP {exc.response.status_code}")
