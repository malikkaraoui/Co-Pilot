"""Service MarketPrice -- stockage et recuperation des prix du marche crowdsources."""

import json
import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone

import numpy as np
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models.market_price import MarketPrice
from app.services.extraction import normalize_region

logger = logging.getLogger(__name__)

CACHE_DURATION_HOURS = 24
MIN_SAMPLE_COUNT = 20  # Minimum de prix standard (voitures courantes)
MIN_SAMPLE_NICHE = 10  # Voitures sportives (300-420 ch)
MIN_SAMPLE_ULTRA_NICHE = 5  # Supercars (420+ ch), hyper rares
MIN_SAMPLE_ABSOLUTE = 5  # Minimum absolu accepte par l'API
IQR_MIN_KEEP = 3  # Seuil de securite IQR : ne pas descendre en-dessous
IQR_MULTIPLIER = 1.5


def get_min_sample_count(make: str, model: str) -> int:
    """Seuil dynamique d'annonces pour l'argus selon le segment du vehicule.

    Les voitures de niche (sportives, supercars) ont tres peu d'annonces sur LBC.
    Appliquer le meme seuil de 20 qu'une Clio les exclut systematiquement.

    Tiers :
    - Standard (< 300 ch) : 20 annonces minimum
    - Niche sportive (300-420 ch) : 10 annonces
    - Ultra-niche (> 420 ch) : 5 annonces (pas de diesel a ce niveau)

    Un override admin (Vehicle.argus_min_samples) a priorite absolue.

    Returns:
        Le seuil minimum d'annonces requis.
    """
    from app.models.vehicle import VehicleSpec
    from app.services.vehicle_lookup import find_vehicle

    vehicle = find_vehicle(make, model)
    if not vehicle:
        return MIN_SAMPLE_COUNT

    # Override admin : priorite absolue
    if vehicle.argus_min_samples is not None:
        return vehicle.argus_min_samples

    # Lookup puissance max dans les specs
    max_hp = (
        db.session.query(func.max(VehicleSpec.power_hp))
        .filter(
            VehicleSpec.vehicle_id == vehicle.id,
            VehicleSpec.power_hp.isnot(None),
        )
        .scalar()
    )

    if max_hp:
        if max_hp > 420:
            return MIN_SAMPLE_ULTRA_NICHE  # 5
        if max_hp > 300:
            return MIN_SAMPLE_NICHE  # 10

    return MIN_SAMPLE_COUNT  # 20


def _strip_accents(text: str) -> str:
    """Supprime les accents et diacritiques (Île → Ile, Côte → Cote).

    Indispensable pour que les comparaisons SQLite lower() (ASCII-only)
    et Python lower() (Unicode-aware) produisent le meme resultat.
    Sans cela, lower('Î') reste 'Î' en SQLite mais devient 'î' en Python.
    """
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_market_text(text: str) -> str:
    """Normalise un texte pour le stockage MarketPrice.

    - strip + collapse espaces multiples
    - supprime les accents (Île → Ile) pour compatibilite SQLite lower()
    - normalise apostrophes (curly → straight)
    - normalise tirets (collapse doubles)
    - conserve la casse originale (pas de title case -- les noms francais
      comme "Provence-Alpes-Cote d'Azur" ont des minuscules apres apostrophe)
    """
    text = unicodedata.normalize("NFKC", text)
    text = _strip_accents(text)
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
    """Expression SQLAlchemy de normalisation textuelle (SQLite compatible).

    Utilise la fonction custom strip_accents() enregistree dans extensions.py
    pour supprimer les diacritiques AVANT lower(). Indispensable car SQLite
    lower() ne gere que ASCII : sans strip_accents, lower('Î') reste 'Î'
    au lieu de produire 'i', ce qui casse Île-de-France.
    """
    return func.lower(
        func.strip_accents(
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


def _enrich_observed_specs(vehicle_id: int, price_details: list[dict]) -> None:
    """Aggregate observed specs (fuel, gearbox, hp) from collected ads."""
    from app.models.vehicle_observed_spec import VehicleObservedSpec

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    spec_counts: dict[tuple[str, str], int] = {}

    for detail in price_details:
        if not isinstance(detail, dict):
            continue
        for spec_type, key in [
            ("fuel", "fuel"),
            ("gearbox", "gearbox"),
            ("horse_power", "horse_power"),
        ]:
            val = detail.get(key)
            if val and str(val).strip():
                normalized = str(val).strip().lower()
                spec_counts[(spec_type, normalized)] = (
                    spec_counts.get((spec_type, normalized), 0) + 1
                )

    for (spec_type, spec_value), count in spec_counts.items():
        existing = VehicleObservedSpec.query.filter_by(
            vehicle_id=vehicle_id,
            spec_type=spec_type,
            spec_value=spec_value,
        ).first()
        if existing:
            existing.count += count
            existing.last_seen_at = now
        else:
            db.session.add(
                VehicleObservedSpec(
                    vehicle_id=vehicle_id,
                    spec_type=spec_type,
                    spec_value=spec_value,
                    count=count,
                    last_seen_at=now,
                )
            )
    db.session.commit()


def store_market_prices(
    make: str,
    model: str,
    year: int,
    region: str,
    prices: list[int],
    fuel: str | None = None,
    precision: int | None = None,
    price_details: list[dict] | None = None,
    search_log: list[dict] | None = None,
    hp_range: str | None = None,
    fiscal_hp: int | None = None,
    lbc_estimate_low: int | None = None,
    lbc_estimate_high: int | None = None,
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
    region = normalize_region(region) or normalize_market_text(region)
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
        "search_steps": search_log,
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
        "hp_range": hp_range,
        "fiscal_hp": fiscal_hp,
        "lbc_estimate_low": lbc_estimate_low,
        "lbc_estimate_high": lbc_estimate_high,
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

    if hp_range:
        filters.append(func.lower(MarketPrice.hp_range) == hp_range.lower())
    else:
        filters.append(MarketPrice.hp_range.is_(None))

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

    # Auto-creation proactive : si le vehicule n'est pas dans le referentiel
    # et qu'on a assez de donnees, le creer automatiquement.
    try:
        from app.services.vehicle_factory import auto_create_vehicle

        vehicle = auto_create_vehicle(make, model)
        if vehicle:
            logger.info(
                "Proactive auto-create: %s %s (id=%d) from market data",
                vehicle.brand,
                vehicle.model,
                vehicle.id,
            )
    except (IntegrityError, SQLAlchemyError):
        # Ne pas faire echouer le store_market_prices pour une auto-creation
        logger.debug("Auto-create skipped for %s %s", make, model, exc_info=True)

    # Enrichir les specs observees si le vehicule existe dans le referentiel
    try:
        from app.services.vehicle_lookup import find_vehicle

        found = find_vehicle(make, model)
        if found and price_details:
            _enrich_observed_specs(found.id, price_details)
    except (IntegrityError, SQLAlchemyError):
        logger.debug("Observed spec enrichment skipped for %s %s", make, model, exc_info=True)

    return mp


def _hp_range_filters(hp_range_key: str | None, exact: bool) -> list:
    """Build hp_range filter clauses for MarketPrice queries.

    Args:
        hp_range_key: Normalized hp_range value (lowercased) or None.
        exact: If True, match the exact hp_range. If False, match hp_range=NULL (generic).

    Returns:
        List of SQLAlchemy filter clauses.
    """
    if hp_range_key and exact:
        return [func.lower(MarketPrice.hp_range) == hp_range_key]
    return [MarketPrice.hp_range.is_(None)]


def get_market_stats(
    make: str,
    model: str,
    year: int,
    region: str,
    fuel: str | None = None,
    hp_range: str | None = None,
) -> MarketPrice | None:
    """Recupere les stats marche pour un vehicule/region.

    Strategie de recherche progressive :
    1. Match exact avec fuel + hp_range (le plus precis)
    2. Fallback hp_range=NULL (generique) sur meme fuel
    3. Fallback fuel=NULL (generique) sur meme year
    4. Fallback annee la plus proche (±3 ans), avec fuel puis sans
    Chaque etape tente d'abord avec hp_range exact, puis hp_range=NULL.

    Les donnees restent valables indefiniment (argus maison).
    Le champ refresh_after indique seulement si un rafraichissement serait souhaitable.

    Args:
        make: Marque du vehicule.
        model: Modele.
        year: Annee.
        region: Region.
        fuel: Type de motorisation (ex. "diesel", "essence"). Optionnel.
        hp_range: Tranche de puissance DIN (ex. "120-150"). Optionnel.

    Returns:
        L'instance MarketPrice si elle existe, None sinon.
    """
    make_key = market_text_key(make)
    model_key = market_text_key(model)
    region_key = market_text_key(normalize_region(region) or region)
    fuel_key = normalize_market_text(fuel).lower() if fuel else None
    hp_range_key = hp_range.strip().lower() if hp_range else None

    base_filters = [
        market_text_key_expr(MarketPrice.make) == make_key,
        market_text_key_expr(MarketPrice.model) == model_key,
        market_text_key_expr(MarketPrice.region) == region_key,
    ]

    # --- Helper: try a query with exact hp_range first, then fallback to hp_range=NULL,
    #     then fallback to ANY hp_range ---
    def _try_with_hp_fallback(extra_filters: list) -> MarketPrice | None:
        """Try query with exact hp_range, then generic (hp_range=NULL), then any."""
        if hp_range_key:
            result = MarketPrice.query.filter(
                *extra_filters, *_hp_range_filters(hp_range_key, exact=True)
            ).first()
            if result:
                return result
        # Fallback to hp_range=NULL (generic)
        result = MarketPrice.query.filter(
            *extra_filters, *_hp_range_filters(hp_range_key, exact=False)
        ).first()
        if result:
            return result
        # Dernier fallback : n'importe quel hp_range (mieux que rien)
        return MarketPrice.query.filter(*extra_filters).first()

    def _try_approx_with_hp_fallback(extra_filters: list) -> MarketPrice | None:
        """Try approx year query with exact hp_range, then generic, then any."""
        if hp_range_key:
            candidates = MarketPrice.query.filter(
                *extra_filters, *_hp_range_filters(hp_range_key, exact=True)
            ).all()
            if candidates:
                return min(candidates, key=lambda mp: abs(mp.year - year))
        # Fallback to hp_range=NULL (generic)
        candidates = MarketPrice.query.filter(
            *extra_filters, *_hp_range_filters(hp_range_key, exact=False)
        ).all()
        if candidates:
            return min(candidates, key=lambda mp: abs(mp.year - year))
        # Dernier fallback : n'importe quel hp_range
        candidates = MarketPrice.query.filter(*extra_filters).all()
        if candidates:
            return min(candidates, key=lambda mp: abs(mp.year - year))
        return None

    # 1. Match exact avec fuel (5+ champs) -- le plus precis
    if fuel_key:
        result = _try_with_hp_fallback(
            [
                *base_filters,
                MarketPrice.year == year,
                func.lower(MarketPrice.fuel) == fuel_key,
            ]
        )
        if result:
            logger.info(
                "MarketPrice exact+fuel: %s %s %d %s %s hp=%s (n=%d)",
                make,
                model,
                year,
                region,
                fuel_key,
                result.hp_range,
                result.sample_count,
            )
            return result

    # 2. Match exact sans fuel (4 champs) -- fallback anciennes donnees ou generique
    # FIX: Si un fuel est demande, on ne doit pas tomber sur un fuel different (ex: diesel → essence)
    # On autorise seulement le fallback sur fuel=None (donnees generiques/anciennes)
    filters_no_fuel = [*base_filters, MarketPrice.year == year]
    if fuel_key:
        filters_no_fuel.append(MarketPrice.fuel.is_(None))

    result = _try_with_hp_fallback(filters_no_fuel)
    if result:
        logger.info(
            "MarketPrice exact: %s %s %d %s hp=%s (n=%d)",
            make,
            model,
            year,
            region,
            result.hp_range,
            result.sample_count,
        )
        return result

    # 3. Fallback : annee la plus proche (±3 ans max), avec fuel d'abord
    year_filters = [*base_filters, MarketPrice.year.between(year - 3, year + 3)]

    if fuel_key:
        result = _try_approx_with_hp_fallback(
            [
                *year_filters,
                func.lower(MarketPrice.fuel) == fuel_key,
            ]
        )
        if result:
            logger.info(
                "MarketPrice approx+fuel: %s %s %d->%d %s %s hp=%s (n=%d)",
                make,
                model,
                year,
                result.year,
                region,
                fuel_key,
                result.hp_range,
                result.sample_count,
            )
            return result

    # 4. Fallback sans fuel (uniquement generic si fuel demande)
    filters_approx_no_fuel = [*year_filters]
    if fuel_key:
        filters_approx_no_fuel.append(MarketPrice.fuel.is_(None))

    result = _try_approx_with_hp_fallback(filters_approx_no_fuel)
    if result:
        logger.info(
            "MarketPrice approx: %s %s %d->%d %s hp=%s (n=%d)",
            make,
            model,
            year,
            result.year,
            region,
            result.hp_range,
            result.sample_count,
        )
        return result

    logger.info(
        "No MarketPrice for %s %s %d %s fuel=%s hp=%s",
        make,
        model,
        year,
        region,
        fuel_key,
        hp_range_key,
    )
    return None
