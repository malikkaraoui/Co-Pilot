"""Service MarketPrice -- stockage et recuperation des prix du marche crowdsources."""

import logging
from datetime import datetime, timedelta, timezone

import numpy as np

from app.extensions import db
from app.models.market_price import MarketPrice

logger = logging.getLogger(__name__)

CACHE_DURATION_HOURS = 24
MIN_SAMPLE_COUNT = 3


def store_market_prices(
    make: str,
    model: str,
    year: int,
    region: str,
    prices: list[int],
) -> MarketPrice:
    """Stocke ou met a jour les prix du marche pour un vehicule/region.

    Calcule les statistiques (min, max, median, mean, std) a partir des prix
    collectes et fait un upsert dans la table market_prices.

    Args:
        make: Marque du vehicule (ex. "Peugeot").
        model: Modele (ex. "208").
        year: Annee du modele.
        region: Region geographique (ex. "Ile-de-France").
        prices: Liste de prix entiers collectes depuis LeBonCoin.

    Returns:
        L'instance MarketPrice creee ou mise a jour.
    """
    arr = np.array(prices, dtype=float)
    now = datetime.now(timezone.utc)

    stats = {
        "price_min": int(np.min(arr)),
        "price_median": int(np.median(arr)),
        "price_mean": int(np.mean(arr)),
        "price_max": int(np.max(arr)),
        "price_std": round(float(np.std(arr)), 2),
        "sample_count": len(prices),
        "collected_at": now,
        "refresh_after": now + timedelta(hours=CACHE_DURATION_HOURS),
    }

    existing = MarketPrice.query.filter_by(
        make=make,
        model=model,
        year=year,
        region=region,
    ).first()

    if existing:
        for key, value in stats.items():
            setattr(existing, key, value)
        db.session.commit()
        logger.info(
            "Updated MarketPrice %s %s %d %s (%d samples)", make, model, year, region, len(prices)
        )
        return existing

    mp = MarketPrice(make=make, model=model, year=year, region=region, **stats)
    db.session.add(mp)
    db.session.commit()
    logger.info(
        "Created MarketPrice %s %s %d %s (%d samples)", make, model, year, region, len(prices)
    )
    return mp


def get_market_stats(make: str, model: str, year: int, region: str) -> MarketPrice | None:
    """Recupere les stats marche pour un vehicule/region.

    Les donnees restent valables indefiniment (argus maison).
    Le champ refresh_after indique seulement si un rafraichissement serait souhaitable.

    Args:
        make: Marque du vehicule.
        model: Modele.
        year: Annee.
        region: Region.

    Returns:
        L'instance MarketPrice si elle existe, None sinon.
    """
    result = MarketPrice.query.filter_by(
        make=make,
        model=model,
        year=year,
        region=region,
    ).first()

    if result:
        logger.debug(
            "MarketPrice found: %s %s %d %s (n=%d)", make, model, year, region, result.sample_count
        )
    else:
        logger.debug("No MarketPrice for %s %s %d %s", make, model, year, region)
    return result
