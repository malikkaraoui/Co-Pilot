"""Service de scoring -- calcule le score global a partir des resultats des filtres."""

import logging

from app.filters.base import FilterResult

logger = logging.getLogger(__name__)


def calculate_score(filter_results: list[FilterResult]) -> tuple[int, bool]:
    """Calcule le score global (0-100) a partir des resultats individuels des filtres.

    Les filtres avec le statut "skip" sont exclus du calcul.
    Si un filtre a ete ignore, le score est marque comme partiel.

    Args:
        filter_results: Liste de FilterResult provenant du moteur.

    Returns:
        Tuple (score 0-100, is_partial).
    """
    if not filter_results:
        return 0, True

    active = [r for r in filter_results if r.status != "skip"]
    skipped = len(filter_results) - len(active)
    is_partial = skipped > 0

    if not active:
        logger.warning("All filters were skipped")
        return 0, True

    total_score = sum(r.score for r in active)
    max_score = len(active)  # Each filter contributes 0.0 to 1.0
    normalized = total_score / max_score

    score = round(normalized * 100)
    score = max(0, min(100, score))

    logger.info(
        "Score: %d/100 (partial=%s, active=%d, skipped=%d)",
        score,
        is_partial,
        len(active),
        skipped,
    )
    return score, is_partial
