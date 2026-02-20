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


class IQRResult:
    """Resultat du filtrage IQR avec stats interquartiles."""

    __slots__ = ("kept", "excluded", "iqr_low", "iqr_high", "q1", "q3", "iqr_mean")

    def __init__(
        self,
        kept: list[int],
        excluded: list[int],
        iqr_low: float,
        iqr_high: float,
        q1: float,
        q3: float,
        iqr_mean: float,
    ):
        self.kept = kept
        self.excluded = excluded
        self.iqr_low = iqr_low
        self.iqr_high = iqr_high
        self.q1 = q1
        self.q3 = q3
        self.iqr_mean = iqr_mean


def _filter_outliers_iqr(prices: list[int]) -> IQRResult:
    """Filtre les outliers via la methode IQR (Interquartile Range).

    Calcule aussi la Moyenne Interquartile (IQR Mean) : la moyenne des prix
    compris entre Q1 et Q3 (les 50% centraux du marche). C'est l'estimateur
    le plus robuste pour un prix de reference :
    - Plus stable que la moyenne (insensible aux extremes)
    - Plus precis que la mediane (prend en compte la distribution reelle)

    Args:
        prices: Liste de prix bruts (deja filtres > 500).

    Returns:
        IQRResult avec kept/excluded prices, bornes IQR, Q1, Q3, et IQR Mean.
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
        kept = sorted(prices)
        excluded = []

    # Moyenne Interquartile : moyenne des prix entre Q1 et Q3 (50% central)
    kept_arr = np.array(kept, dtype=float)
    p25 = float(np.percentile(kept_arr, 25))
    p75 = float(np.percentile(kept_arr, 75))
    middle = kept_arr[(kept_arr >= p25) & (kept_arr <= p75)]
    iqr_mean = float(np.mean(middle)) if len(middle) >= 1 else float(np.mean(kept_arr))

    return IQRResult(
        kept=sorted(kept),
        excluded=sorted(excluded),
        iqr_low=iqr_low,
        iqr_high=iqr_high,
        q1=p25,
        q3=p75,
        iqr_mean=iqr_mean,
    )


def store_market_prices(
    make: str,
    model: str,
    year: int,
    region: str,
    prices: list[int],
    fuel: str | None = None,
    precision: int | None = None,
    price_details: list[dict] | None = None,
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

    # Filtrage IQR des outliers + calcul IQR Mean
    iqr = _filter_outliers_iqr(prices)
    arr = np.array(iqr.kept, dtype=float)
    now = datetime.now(timezone.utc)

    # Construire un index price→details pour retrouver year/km/fuel par prix
    details_by_price: dict[int, list[dict]] = {}
    if price_details:
        for d in price_details:
            p = d.get("price", 0)
            details_by_price.setdefault(p, []).append(d)

    def _enrich(price_list: list[int]) -> list[dict]:
        """Associe chaque prix a ses details (year, km, fuel) si disponibles."""
        enriched = []
        used: dict[int, int] = {}  # price → index consumed
        for p in price_list:
            idx = used.get(p, 0)
            candidates = details_by_price.get(p, [])
            if idx < len(candidates):
                enriched.append(candidates[idx])
                used[p] = idx + 1
            else:
                enriched.append({"price": p})
        return enriched

    kept_details = _enrich(iqr.kept) if price_details else None
    excluded_details = _enrich(iqr.excluded) if price_details else None

    details = {
        "raw_prices": sorted(prices),
        "kept_prices": iqr.kept,
        "excluded_prices": iqr.excluded,
        "kept_details": kept_details,
        "excluded_details": excluded_details,
        "iqr_low": round(iqr.iqr_low, 0),
        "iqr_high": round(iqr.iqr_high, 0),
        "q1": round(iqr.q1, 0),
        "q3": round(iqr.q3, 0),
        "iqr_mean": round(iqr.iqr_mean, 0),
        "raw_count": len(prices),
        "kept_count": len(iqr.kept),
        "excluded_count": len(iqr.excluded),
        "method": "iqr_mean",
        "precision": precision,
    }

    stats = {
        "price_min": int(np.min(arr)),
        "price_median": int(np.median(arr)),
        "price_mean": int(np.mean(arr)),
        "price_max": int(np.max(arr)),
        "price_std": round(float(np.std(arr)), 2),
        "price_iqr_mean": int(round(iqr.iqr_mean)),
        "price_p25": int(round(iqr.q1)),
        "price_p75": int(round(iqr.q3)),
        "sample_count": len(iqr.kept),
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

    log_msg = "%s MarketPrice %s %s %d %s fuel=%s (n=%d/%d, iqr_mean=%d, median=%d, P25=%d, P75=%d)"
    log_args = (
        make,
        model,
        year,
        region,
        fuel,
        len(iqr.kept),
        len(prices),
        stats["price_iqr_mean"],
        stats["price_median"],
        stats["price_p25"],
        stats["price_p75"],
    )

    if existing:
        existing.make = make
        existing.model = model
        existing.region = region
        existing.fuel = fuel
        for key, value in stats.items():
            setattr(existing, key, value)
        db.session.commit()
        logger.info(log_msg, "Updated", *log_args)
        return existing

    mp = MarketPrice(make=make, model=model, year=year, region=region, fuel=fuel, **stats)
    db.session.add(mp)
    db.session.commit()
    logger.info(log_msg, "Created", *log_args)
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

    # 2. Match exact sans fuel (4 champs) -- fallback anciennes donnees ou generique
    filters_no_fuel = [
        *base_filters,
        MarketPrice.year == year,
    ]
    # FIX: Si un fuel est demande, on ne doit pas tomber sur un fuel different (ex: diesel → essence)
    # On autorise seulement le fallback sur fuel=None (donnees generiques/anciennes)
    if fuel_key:
        filters_no_fuel.append(MarketPrice.fuel.is_(None))

    result = MarketPrice.query.filter(*filters_no_fuel).first()

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

    # 4. Fallback sans fuel (uniquement generic si fuel demande)
    filters_approx_no_fuel = [*year_filters]
    if fuel_key:
        filters_approx_no_fuel.append(MarketPrice.fuel.is_(None))

    candidates = MarketPrice.query.filter(*filters_approx_no_fuel).all()
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
