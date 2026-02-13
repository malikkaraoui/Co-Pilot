"""Service MarketPrice -- stockage et recuperation des prix du marche crowdsources."""

import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone

import numpy as np
from sqlalchemy import func

from app.extensions import db
from app.models.market_price import MarketPrice

logger = logging.getLogger(__name__)

CACHE_DURATION_HOURS = 24
MIN_SAMPLE_COUNT = 3


def normalize_market_text(text: str) -> str:
    """Normalise un texte pour le stockage MarketPrice.

    - strip + collapse espaces multiples
    - normalise apostrophes (curly → straight)
    - normalise tirets (collapse doubles)
    - conserve la casse originale (pas de title case -- les noms francais
      comme "Provence-Alpes-Côte d'Azur" ont des minuscules apres apostrophe)
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    # Apostrophes curly → straight
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    # Tirets doubles → simple
    text = re.sub(r"-{2,}", "-", text)
    return text


def market_text_key(text: str) -> str:
    """Cle de comparaison stable pour make/model/region (case-insensitive)."""
    return normalize_market_text(text).lower()


def market_text_key_expr(column):
    """Expression SQLAlchemy de normalisation textuelle (SQLite compatible)."""
    # Note: on reproduit seulement les transformations faisables en SQL.
    return func.lower(
        func.replace(
            func.replace(
                func.trim(column),
                "\u2019",
                "'",
            ),
            "\u2018",
            "'",
        )
    )


def store_market_prices(
    make: str,
    model: str,
    year: int,
    region: str,
    prices: list[int],
) -> MarketPrice:
    """Stocke ou met a jour les prix du marche pour un vehicule/region.

    Normalise make/model/region avant stockage pour garantir des matchs fiables.

    Args:
        make: Marque du vehicule (ex. "Peugeot").
        model: Modele (ex. "208").
        year: Annee du modele.
        region: Region geographique (ex. "Ile-de-France").
        prices: Liste de prix entiers collectes depuis LeBonCoin.

    Returns:
        L'instance MarketPrice creee ou mise a jour.
    """
    make = normalize_market_text(make)
    model = normalize_market_text(model)
    region = normalize_market_text(region)

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

    existing = MarketPrice.query.filter(
        market_text_key_expr(MarketPrice.make) == market_text_key(make),
        market_text_key_expr(MarketPrice.model) == market_text_key(model),
        MarketPrice.year == year,
        market_text_key_expr(MarketPrice.region) == market_text_key(region),
    ).first()

    if existing:
        # Mettre a jour aussi les noms normalises
        existing.make = make
        existing.model = model
        existing.region = region
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

    Strategie de recherche progressive :
    1. Match exact (make + model + year + region)
    2. Fallback : make + model + region, annee la plus proche

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
    make_key = market_text_key(make)
    model_key = market_text_key(model)
    region_key = market_text_key(region)

    # 1. Match exact (4 champs)
    result = MarketPrice.query.filter(
        market_text_key_expr(MarketPrice.make) == make_key,
        market_text_key_expr(MarketPrice.model) == model_key,
        MarketPrice.year == year,
        market_text_key_expr(MarketPrice.region) == region_key,
    ).first()

    if result:
        logger.info(
            "MarketPrice exact: %s %s %d %s (n=%d)", make, model, year, region, result.sample_count
        )
        return result

    # 2. Fallback : make + model + region, annee la plus proche (±3 ans max)
    candidates = MarketPrice.query.filter(
        market_text_key_expr(MarketPrice.make) == make_key,
        market_text_key_expr(MarketPrice.model) == model_key,
        market_text_key_expr(MarketPrice.region) == region_key,
        MarketPrice.year.between(year - 3, year + 3),
    ).all()

    if candidates:
        result = min(candidates, key=lambda mp: abs(mp.year - year))
        logger.info(
            "MarketPrice approx: %s %s %d->%d %s (n=%d)",
            make,
            model,
            year,
            result.year,
            region,
            result.sample_count,
        )
        return result

    logger.info("No MarketPrice for %s %s %d %s", make, model, year, region)
    return None
