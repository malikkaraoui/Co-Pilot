"""Service MarketPrice -- stockage et recuperation des prix du marche crowdsources."""

import json
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
MIN_SAMPLE_COUNT = 20  # Minimum de prix acceptes par l'API
IQR_MIN_KEEP = 3  # Seuil de securite IQR : ne pas descendre en-dessous
IQR_MULTIPLIER = 1.5


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


def _filter_outliers_iqr(prices: list[int]) -> tuple[list[int], list[int], float, float]:
    """Filtre les outliers via la methode IQR (Interquartile Range).

    Args:
        prices: Liste de prix bruts (deja filtres > 500).

    Returns:
        (kept_prices, excluded_prices, iqr_low, iqr_high)
    """
    arr = np.array(sorted(prices), dtype=float)
    q1 = float(np.percentile(arr, 25))
    q3 = float(np.percentile(arr, 75))
    iqr = q3 - q1

    # Bornes : on accepte [Q1 - 1.5*IQR, Q3 + 1.5*IQR]
    iqr_low = q1 - IQR_MULTIPLIER * iqr
    iqr_high = q3 + IQR_MULTIPLIER * iqr

    kept = [p for p in prices if iqr_low <= p <= iqr_high]
    excluded = [p for p in prices if p < iqr_low or p > iqr_high]

    # Si tout est exclu (ex: echantillon trop petit), garder tout
    if len(kept) < IQR_MIN_KEEP:
        return sorted(prices), [], iqr_low, iqr_high

    return sorted(kept), sorted(excluded), iqr_low, iqr_high


def store_market_prices(
    make: str,
    model: str,
    year: int,
    region: str,
    prices: list[int],
    fuel: str | None = None,
    precision: int | None = None,
) -> MarketPrice:
    """Stocke ou met a jour les prix du marche pour un vehicule/region.

    Utilise le filtrage IQR pour eliminer les outliers (prix aberrants).
    Les stats (min, median, mean, max, std) sont calculees sur les prix filtres.
    Les details du calcul (prix bruts, filtres, exclus) sont stockes en JSON.

    Args:
        make: Marque du vehicule (ex. "Peugeot").
        model: Modele (ex. "208").
        year: Annee du modele.
        region: Region geographique (ex. "Ile-de-France").
        prices: Liste de prix entiers collectes depuis LeBonCoin.
        fuel: Type de motorisation (ex. "essence", "diesel"). Optionnel.

    Returns:
        L'instance MarketPrice creee ou mise a jour.
    """
    make = normalize_market_text(make)
    model = normalize_market_text(model)
    region = normalize_market_text(region)
    fuel = normalize_market_text(fuel).lower() if fuel else None

    # Filtrage IQR des outliers
    kept, excluded, iqr_low, iqr_high = _filter_outliers_iqr(prices)
    arr = np.array(kept, dtype=float)
    now = datetime.now(timezone.utc)

    details = {
        "raw_prices": sorted(prices),
        "kept_prices": kept,
        "excluded_prices": excluded,
        "iqr_low": round(iqr_low, 0),
        "iqr_high": round(iqr_high, 0),
        "raw_count": len(prices),
        "kept_count": len(kept),
        "excluded_count": len(excluded),
        "method": "iqr",
        "precision": precision,
    }

    stats = {
        "price_min": int(np.min(arr)),
        "price_median": int(np.median(arr)),
        "price_mean": int(np.mean(arr)),
        "price_max": int(np.max(arr)),
        "price_std": round(float(np.std(arr)), 2),
        "sample_count": len(kept),
        "precision": precision,
        "calculation_details": json.dumps(details),
        "collected_at": now,
        "refresh_after": now + timedelta(hours=CACHE_DURATION_HOURS),
    }

    # Recherche existante : si fuel est fourni, chercher par fuel d'abord
    filters = [
        market_text_key_expr(MarketPrice.make) == market_text_key(make),
        market_text_key_expr(MarketPrice.model) == market_text_key(model),
        MarketPrice.year == year,
        market_text_key_expr(MarketPrice.region) == market_text_key(region),
    ]
    if fuel:
        filters.append(func.lower(MarketPrice.fuel) == fuel)
    else:
        filters.append(MarketPrice.fuel.is_(None))

    existing = MarketPrice.query.filter(*filters).first()

    if existing:
        existing.make = make
        existing.model = model
        existing.region = region
        existing.fuel = fuel
        for key, value in stats.items():
            setattr(existing, key, value)
        db.session.commit()
        logger.info(
            "Updated MarketPrice %s %s %d %s fuel=%s (%d/%d kept, %d excluded)",
            make,
            model,
            year,
            region,
            fuel,
            len(kept),
            len(prices),
            len(excluded),
        )
        return existing

    mp = MarketPrice(make=make, model=model, year=year, region=region, fuel=fuel, **stats)
    db.session.add(mp)
    db.session.commit()
    logger.info(
        "Created MarketPrice %s %s %d %s fuel=%s (%d/%d kept, %d excluded)",
        make,
        model,
        year,
        region,
        fuel,
        len(kept),
        len(prices),
        len(excluded),
    )
    return mp


def get_market_stats(
    make: str, model: str, year: int, region: str, fuel: str | None = None
) -> MarketPrice | None:
    """Recupere les stats marche pour un vehicule/region.

    Strategie de recherche progressive :
    1. Match exact avec fuel (make + model + year + region + fuel)
    2. Match exact sans fuel (make + model + year + region)
    3. Fallback : make + model + region, annee la plus proche (avec puis sans fuel)

    Les donnees restent valables indefiniment (argus maison).
    Le champ refresh_after indique seulement si un rafraichissement serait souhaitable.

    Args:
        make: Marque du vehicule.
        model: Modele.
        year: Annee.
        region: Region.
        fuel: Type de motorisation (ex. "diesel", "essence"). Optionnel.

    Returns:
        L'instance MarketPrice si elle existe, None sinon.
    """
    make_key = market_text_key(make)
    model_key = market_text_key(model)
    region_key = market_text_key(region)
    fuel_key = fuel.strip().lower() if fuel else None

    base_filters = [
        market_text_key_expr(MarketPrice.make) == make_key,
        market_text_key_expr(MarketPrice.model) == model_key,
        market_text_key_expr(MarketPrice.region) == region_key,
    ]

    # 1. Match exact avec fuel (5 champs) -- le plus precis
    if fuel_key:
        result = MarketPrice.query.filter(
            *base_filters,
            MarketPrice.year == year,
            func.lower(MarketPrice.fuel) == fuel_key,
        ).first()
        if result:
            logger.info(
                "MarketPrice exact+fuel: %s %s %d %s %s (n=%d)",
                make,
                model,
                year,
                region,
                fuel_key,
                result.sample_count,
            )
            return result

    # 2. Match exact sans fuel (4 champs) -- fallback anciennes donnees
    result = MarketPrice.query.filter(
        *base_filters,
        MarketPrice.year == year,
    ).first()

    if result:
        logger.info(
            "MarketPrice exact: %s %s %d %s (n=%d)", make, model, year, region, result.sample_count
        )
        return result

    # 3. Fallback : annee la plus proche (±3 ans max), avec fuel d'abord
    year_filters = [*base_filters, MarketPrice.year.between(year - 3, year + 3)]

    if fuel_key:
        candidates = MarketPrice.query.filter(
            *year_filters,
            func.lower(MarketPrice.fuel) == fuel_key,
        ).all()
        if candidates:
            result = min(candidates, key=lambda mp: abs(mp.year - year))
            logger.info(
                "MarketPrice approx+fuel: %s %s %d->%d %s %s (n=%d)",
                make,
                model,
                year,
                result.year,
                region,
                fuel_key,
                result.sample_count,
            )
            return result

    # 4. Fallback sans fuel
    candidates = MarketPrice.query.filter(*year_filters).all()
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

    logger.info("No MarketPrice for %s %s %d %s fuel=%s", make, model, year, region, fuel_key)
    return None
