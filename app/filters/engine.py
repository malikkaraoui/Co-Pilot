"""FilterEngine -- orchestre l'execution des filtres en parallele."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import httpx
from flask import current_app

from app.errors import FilterError
from app.filters.base import BaseFilter, FilterResult

logger = logging.getLogger(__name__)

MAX_WORKERS = 9


class FilterEngine:
    """Execute les filtres enregistres en parallele et collecte les resultats.

    Usage:
        engine = FilterEngine()
        engine.register(L1ExtractionFilter())
        engine.register(L2ReferentielFilter())
        results = engine.run_all(ad_data)
    """

    def __init__(self):
        self._filters: list[BaseFilter] = []

    def register(self, filter_instance: BaseFilter) -> None:
        """Enregistre un filtre pour execution."""
        self._filters.append(filter_instance)
        logger.debug("Registered filter %s", filter_instance.filter_id)

    @property
    def filter_count(self) -> int:
        return len(self._filters)

    def _execute_filter(self, filt: BaseFilter, data: dict[str, Any], app=None) -> FilterResult:
        """Execute un filtre avec gestion d'erreur et contexte Flask."""
        try:
            # Propager le contexte Flask dans les threads pour les filtres
            # qui font des requetes en base (L2, L4, L5)
            if app is not None:
                with app.app_context():
                    result = filt.run(data)
            else:
                result = filt.run(data)
            logger.info(
                "Filter %s: status=%s score=%.2f",
                filt.filter_id,
                result.status,
                result.score,
            )
            return result
        except FilterError as exc:
            logger.warning("Filter %s raised FilterError: %s", filt.filter_id, exc)
            return FilterResult(
                filter_id=filt.filter_id,
                status="skip",
                score=0.0,
                message="Analyse partielle — ce filtre n'a pas pu s'exécuter",
                details={"error": str(exc)},
            )
        except (KeyError, ValueError, AttributeError, TypeError, OSError, httpx.HTTPError) as exc:
            logger.error(
                "Filter %s raised unexpected %s: %s",
                filt.filter_id,
                type(exc).__name__,
                exc,
            )
            return FilterResult(
                filter_id=filt.filter_id,
                status="skip",
                score=0.0,
                message="Erreur inattendue — ce filtre a été ignoré",
                details={"error": type(exc).__name__, "detail": str(exc)},
            )

    def run_all(self, data: dict[str, Any]) -> list[FilterResult]:
        """Execute tous les filtres en parallele (ThreadPoolExecutor).

        Args:
            data: Donnees normalisees de l'annonce (extraction service).

        Returns:
            Liste de FilterResult, un par filtre enregistre.
        """
        if not self._filters:
            logger.warning("No filters registered in engine")
            return []

        results: list[FilterResult] = []
        workers = min(MAX_WORKERS, len(self._filters))

        # Capturer l'app Flask pour la passer aux threads
        try:
            app = current_app._get_current_object()
        except RuntimeError:
            app = None

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_filter = {
                executor.submit(self._execute_filter, filt, data, app): filt
                for filt in self._filters
            }
            for future in as_completed(future_to_filter):
                filt = future_to_filter[future]
                try:
                    results.append(future.result())
                except (
                    KeyError,
                    ValueError,
                    AttributeError,
                    TypeError,
                    OSError,
                    httpx.HTTPError,
                ) as exc:
                    logger.error(
                        "Filter %s thread crashed: %s: %s",
                        filt.filter_id,
                        type(exc).__name__,
                        exc,
                    )
                    results.append(
                        FilterResult(
                            filter_id=filt.filter_id,
                            status="skip",
                            score=0.0,
                            message="Erreur inattendue — ce filtre a été ignoré",
                            details={"error": type(exc).__name__},
                        )
                    )

        # Trier par filter_id pour un ordre constant
        results.sort(key=lambda r: r.filter_id)
        logger.info("Engine ran %d filters", len(results))
        return results
