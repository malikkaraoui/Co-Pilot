"""Filtre L10 Anciennete annonce -- analyse la duree de mise en vente et detecte les annonces stagnantes.

Le principe : si une annonce est en ligne depuis longtemps, c'est un signal.
Soit le prix est trop haut (les acheteurs passent leur tour), soit il y a
un probleme cache qui fait fuir les visiteurs en visite.

Le seuil varie selon le segment du vehicule :
- Un vehicule populaire a 8 000 EUR devrait partir en ~3 semaines
- Un vehicule premium a 60 000 EUR peut rester 2-3 mois sans que ce soit anormal

Quand on a assez de data historique (scans precedents), on utilise la mediane
reelle du marche au lieu des seuils statiques.
"""

import logging
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any

from app.filters.base import BaseFilter, FilterResult

logger = logging.getLogger(__name__)

# Seuils par tranche de prix (proxy du segment vehicule).
# Nombre de jours au-dela duquel une annonce est consideree "au-dessus de la normale".
PRICE_THRESHOLDS: list[tuple[int, int]] = [
    # (prix_max, seuil_jours)
    (10_000, 21),  # Vehicules populaires/entree de gamme
    (25_000, 35),  # Milieu de gamme
    (50_000, 50),  # Haut de gamme
]
PREMIUM_THRESHOLD_DAYS = 75  # >50k EUR : premium/niche, temps de vente plus long

# Nombre minimum de scans historiques pour utiliser la mediane marche
# En dessous, les stats ne sont pas fiables
MIN_MARKET_SAMPLES = 5

# Fenetre de temps pour les scans historiques (jours)
# On ne regarde que les 3 derniers mois pour rester representatif
MARKET_LOOKBACK_DAYS = 90


def _threshold_for_price(price_eur: int | None) -> int:
    """Retourne le seuil de jours en fonction du prix du vehicule.

    Plus le vehicule est cher, plus on tolere un temps de vente long.
    """
    if price_eur is None:
        return 35  # fallback milieu de gamme

    for max_price, threshold in PRICE_THRESHOLDS:
        if price_eur < max_price:
            return threshold
    return PREMIUM_THRESHOLD_DAYS


def _get_market_median_days(make: str, model: str) -> int | None:
    """Calcule la mediane des days_online pour un make/model depuis ScanLog.

    Utilise les scans des 90 derniers jours pour ce modele.
    Retourne None si pas assez de donnees (<MIN_MARKET_SAMPLES).
    """
    from app.models.scan import ScanLog

    cutoff = datetime.now(timezone.utc) - timedelta(days=MARKET_LOOKBACK_DAYS)

    rows = (
        ScanLog.query.filter(
            ScanLog.vehicle_make.ilike(make),
            ScanLog.vehicle_model.ilike(model),
            ScanLog.days_online.isnot(None),
            ScanLog.created_at >= cutoff,
        )
        .with_entities(ScanLog.days_online)
        .all()
    )

    values = [r.days_online for r in rows if r.days_online is not None and r.days_online >= 0]

    if len(values) < MIN_MARKET_SAMPLES:
        return None

    return round(statistics.median(values))


class L10ListingAgeFilter(BaseFilter):
    """Analyse l'anciennete de l'annonce et detecte les annonces stagnantes.

    Le seuil est dynamique :
    - Si on a assez de scans historiques pour ce modele, on utilise la mediane reelle
    - Sinon, on utilise un seuil statique base sur le prix (proxy du segment)

    Malus supplementaire si l'annonce a ete republiee (le vendeur triche
    pour paraitre recent, ce qui est un red flag supplementaire).
    """

    filter_id = "L10"

    def run(self, data: dict[str, Any]) -> FilterResult:
        days_online = data.get("days_online")

        if days_online is None:
            return self.skip("Ancienneté de l'annonce non disponible")

        republished = data.get("republished", False)
        price_eur = data.get("price_eur")
        make = data.get("make") or ""
        model = data.get("model") or ""

        # Determiner le seuil : marche reel si assez de data, sinon fallback prix
        market_median = None
        threshold_source = "prix"
        if make and model:
            market_median = _get_market_median_days(make, model)

        if market_median is not None and market_median > 0:
            threshold = market_median
            threshold_source = "marche"
        else:
            threshold = _threshold_for_price(price_eur)

        # Ratio anciennete / seuil : permet de comparer des segments differents
        ratio = days_online / threshold if threshold > 0 else 0

        # Scoring par ratio : plus le ratio est eleve, plus c'est suspect
        if ratio <= 0.3:
            score = 1.0
            status = "pass"
            message = f"Annonce récente ({days_online} jour{'s' if days_online > 1 else ''})"
        elif ratio <= 1.0:
            score = 0.8
            status = "pass"
            message = f"Durée de mise en vente normale ({days_online} jours, seuil {threshold}j)"
        elif ratio <= 2.0:
            score = 0.5
            status = "warning"
            message = (
                f"Annonce en ligne depuis {days_online} jours (seuil {threshold}j pour ce segment)"
            )
        else:
            score = 0.3
            status = "warning"
            message = (
                f"Annonce stagnante : {days_online} jours en ligne "
                f"(seuil {threshold}j pour ce segment)"
            )

        # Malus republication : le vendeur a tente de "remettre a zero" l'anciennete
        # C'est un signal supplementaire de difficulte a vendre
        if republished:
            if ratio > 2.0:
                score = 0.2
                status = "fail"
                message += " — republié pour paraître récent"
            elif ratio > 1.0:
                score = max(score - 0.1, 0.2)
                message += " — republié pour paraître récent"
            else:
                message += " (republié)"

        return FilterResult(
            filter_id=self.filter_id,
            status=status,
            score=round(score, 2),
            message=message,
            details={
                "days_online": days_online,
                "threshold_days": threshold,
                "threshold_source": threshold_source,
                "ratio": round(ratio, 2),
                "republished": republished,
                **({"market_median_days": market_median} if market_median is not None else {}),
            },
        )
