"""Service de scoring -- calcule le score global pondere a partir des resultats des filtres."""

import logging

from app.filters.base import FilterResult

logger = logging.getLogger(__name__)

# Poids de chaque filtre dans le score global.
# Les filtres critiques (L2 modele, L4 prix) pesent x2.
# Total = 12.0
FILTER_WEIGHTS: dict[str, float] = {
    "L1": 1.0,  # Completude des donnees
    "L2": 2.0,  # Modele reconnu (CRITIQUE)
    "L3": 1.5,  # Coherence km/annee
    "L4": 2.0,  # Prix vs Argus (CRITIQUE)
    "L5": 1.5,  # Analyse statistique
    "L6": 0.5,  # Telephone (signal faible)
    "L7": 1.0,  # SIRET vendeur
    "L8": 1.0,  # Detection import
    "L9": 1.5,  # Evaluation globale
    "L10": 1.0,  # Anciennete annonce
}


def calculate_score(filter_results: list[FilterResult]) -> tuple[int, bool]:
    """Calcule le score global pondere (0-100) a partir des resultats des filtres.

    Scoring pondere : chaque filtre a un poids (FILTER_WEIGHTS).
    Les filtres "skip" comptent dans le denominateur (poids) mais
    contribuent 0 au numerateur -- cela penalise les donnees manquantes.

    Args:
        filter_results: Liste de FilterResult provenant du moteur.

    Returns:
        Tuple (score 0-100, is_partial).
    """
    if not filter_results:
        return 0, True

    weighted_sum = 0.0
    total_weight = 0.0
    skipped = 0

    for r in filter_results:
        w = FILTER_WEIGHTS.get(r.filter_id, 1.0)
        total_weight += w

        if r.status == "skip":
            skipped += 1
            # Skip : poids dans le denominateur, 0 dans le numerateur
            continue

        weighted_sum += w * r.score

    is_partial = skipped > 0

    if total_weight == 0:
        logger.warning("All filters were skipped")
        return 0, True

    normalized = weighted_sum / total_weight
    score = round(normalized * 100)
    score = max(0, min(100, score))

    logger.info(
        "Score: %d/100 (partial=%s, skipped=%d, weighted_sum=%.2f, total_weight=%.1f)",
        score,
        is_partial,
        skipped,
        weighted_sum,
        total_weight,
    )
    return score, is_partial
