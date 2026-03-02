"""Service CollectionJobAS24 -- gestion de la file d'attente pour AutoScout24."""

import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.collection_job_as24 import CollectionJobAS24
from app.models.market_price import MarketPrice
from app.services.market_service import market_text_key, market_text_key_expr

logger = logging.getLogger(__name__)

FRESHNESS_DAYS = 7
MAX_ATTEMPTS = 3
ASSIGNMENT_TIMEOUT_MINUTES = 30
LOW_DATA_FAIL_THRESHOLD = 3

# Cache en memoire pour eviter de re-expand le meme vehicule a chaque requete.
_expand_cache: dict[str, float] = {}
_EXPAND_COOLDOWN_SECONDS = 300  # 5 minutes

# Regions AS24 par pays (CH = cantons, autres = national uniquement)
SWISS_CANTONS = [
    "Zurich",
    "Berne",
    "Lucerne",
    "Uri",
    "Schwyz",
    "Obwald",
    "Nidwald",
    "Glaris",
    "Zoug",
    "Fribourg",
    "Soleure",
    "Bale-Ville",
    "Bale-Campagne",
    "Schaffhouse",
    "Appenzell Rhodes-Exterieures",
    "Appenzell Rhodes-Interieures",
    "Saint-Gall",
    "Grisons",
    "Argovie",
    "Thurgovie",
    "Tessin",
    "Vaud",
    "Valais",
    "Neuchatel",
    "Geneve",
    "Jura",
]

# Mapping TLD → currency
TLD_TO_CURRENCY = {
    "ch": "CHF",
}

# Mapping TLD → country code ISO
TLD_TO_COUNTRY = {
    "ch": "CH",
    "de": "DE",
    "fr": "FR",
    "it": "IT",
    "at": "AT",
    "es": "ES",
    "be": "BE",
    "nl": "NL",
    "lu": "LU",
}

FUEL_OPPOSITES = {"diesel": "essence", "essence": "diesel"}
GEARBOX_OPPOSITES = {
    "manual": "automatique",
    "manuelle": "automatique",
    "automatique": "manuelle",
    "auto": "manuelle",
}


# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------


def _get_currency(tld: str) -> str:
    """Derive la monnaie depuis le TLD."""
    return TLD_TO_CURRENCY.get(tld.lower(), "EUR")


def _get_regions_for_country_as24(country: str) -> list[str]:
    """Retourne la liste de regions pour l'expansion AS24.

    CH = 26 cantons, autres pays = juste ['national'] (pas de granularite).
    """
    if country.upper() == "CH":
        return SWISS_CANTONS
    return ["national"]


def _get_search_strategy(country: str, region: str) -> str:
    """Determine la search_strategy selon le contexte."""
    if country.upper() == "CH" and region != "national":
        return "canton"
    return "national"


def _has_fresh_market_price_as24(
    make: str,
    model: str,
    year: int,
    region: str,
    fuel: str | None,
    hp_range: str | None,
    country: str,
) -> bool:
    """Verifie si un MarketPrice frais (< FRESHNESS_DAYS) existe pour ce combo."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=FRESHNESS_DAYS)

    filters = [
        market_text_key_expr(MarketPrice.make) == market_text_key(make),
        market_text_key_expr(MarketPrice.model) == market_text_key(model),
        MarketPrice.year == year,
        market_text_key_expr(MarketPrice.region) == market_text_key(region),
        func.coalesce(MarketPrice.country, "FR") == country.upper(),
        MarketPrice.collected_at >= cutoff,
    ]

    if fuel:
        filters.append(MarketPrice.fuel == fuel.lower())
    else:
        filters.append(MarketPrice.fuel.is_(None))

    if hp_range:
        filters.append(MarketPrice.hp_range == hp_range)
    else:
        filters.append(MarketPrice.hp_range.is_(None))

    return db.session.query(MarketPrice.id).filter(*filters).first() is not None


def _job_exists_as24(
    make: str,
    model: str,
    year: int,
    region: str,
    fuel: str | None,
    gearbox: str | None,
    hp_range: str | None,
    country: str,
    tld: str,
) -> bool:
    """Verifie si un CollectionJobAS24 identique existe deja (actif OU failed recent)."""
    failed_cutoff = datetime.now(timezone.utc) - timedelta(days=FRESHNESS_DAYS)

    filters = [
        func.lower(CollectionJobAS24.make) == make.strip().lower(),
        func.lower(CollectionJobAS24.model) == model.strip().lower(),
        CollectionJobAS24.year == year,
        CollectionJobAS24.region == region,
        CollectionJobAS24.country == country.upper(),
        CollectionJobAS24.tld == tld.lower(),
        db.or_(
            CollectionJobAS24.status.in_(("pending", "assigned")),
            db.and_(
                CollectionJobAS24.status == "failed",
                CollectionJobAS24.created_at >= failed_cutoff,
            ),
        ),
    ]

    for col, val in [
        (CollectionJobAS24.fuel, fuel),
        (CollectionJobAS24.gearbox, gearbox),
        (CollectionJobAS24.hp_range, hp_range),
    ]:
        if val is None:
            filters.append(col.is_(None))
        else:
            filters.append(col == val)

    return db.session.query(CollectionJobAS24.id).filter(*filters).first() is not None


def _find_old_failed_job_as24(
    make: str,
    model: str,
    year: int,
    region: str,
    fuel: str | None,
    gearbox: str | None,
    hp_range: str | None,
    country: str,
    tld: str,
) -> CollectionJobAS24 | None:
    """Cherche un job failed ancien (> FRESHNESS_DAYS) pour le recycler."""
    failed_cutoff = datetime.now(timezone.utc) - timedelta(days=FRESHNESS_DAYS)

    filters = [
        func.lower(CollectionJobAS24.make) == make.strip().lower(),
        func.lower(CollectionJobAS24.model) == model.strip().lower(),
        CollectionJobAS24.year == year,
        CollectionJobAS24.region == region,
        CollectionJobAS24.country == country.upper(),
        CollectionJobAS24.tld == tld.lower(),
        CollectionJobAS24.status == "failed",
        CollectionJobAS24.created_at < failed_cutoff,
    ]

    for col, val in [
        (CollectionJobAS24.fuel, fuel),
        (CollectionJobAS24.gearbox, gearbox),
        (CollectionJobAS24.hp_range, hp_range),
    ]:
        if val is None:
            filters.append(col.is_(None))
        else:
            filters.append(col == val)

    return CollectionJobAS24.query.filter(*filters).first()


def _try_create_job_as24(
    make: str,
    model: str,
    year: int,
    region: str,
    fuel: str | None,
    gearbox: str | None,
    hp_range: str | None,
    priority: int,
    source_vehicle: str,
    country: str,
    tld: str,
    slug_make: str,
    slug_model: str,
    search_strategy: str | None = None,
) -> CollectionJobAS24 | None:
    """Tente de creer un CollectionJobAS24. Retourne None si doublon ou deja frais."""
    country = country.upper()

    if _has_fresh_market_price_as24(make, model, year, region, fuel, hp_range, country):
        return None

    if _job_exists_as24(make, model, year, region, fuel, gearbox, hp_range, country, tld):
        return None

    # Recycler un vieux job failed
    old = _find_old_failed_job_as24(
        make,
        model,
        year,
        region,
        fuel,
        gearbox,
        hp_range,
        country,
        tld,
    )
    if old:
        old.status = "pending"
        old.priority = priority
        old.attempts = 0
        old.assigned_at = None
        old.completed_at = None
        old.created_at = datetime.now(timezone.utc)
        old.source_vehicle = source_vehicle
        old.slug_make = slug_make
        old.slug_model = slug_model
        return old

    strategy = search_strategy or _get_search_strategy(country, region)
    currency = _get_currency(tld)

    job = CollectionJobAS24(
        make=make,
        model=model,
        year=year,
        region=region,
        fuel=fuel,
        gearbox=gearbox,
        hp_range=hp_range,
        priority=priority,
        source_vehicle=source_vehicle,
        country=country,
        tld=tld,
        slug_make=slug_make,
        slug_model=slug_model,
        search_strategy=strategy,
        currency=currency,
    )

    nested = db.session.begin_nested()
    try:
        db.session.add(job)
        nested.commit()
    except IntegrityError:
        nested.rollback()
        return None

    return job


# ---------------------------------------------------------------------------
# Low-data detection & zombie cleanup
# ---------------------------------------------------------------------------


def _get_low_data_vehicles_as24(
    country: str | None = None,
    tld: str | None = None,
) -> set[tuple[str, str, str, str]]:
    """Identifie les vehicules AS24 avec >= LOW_DATA_FAIL_THRESHOLD fails recents.

    Retourne un set de (make_lower, model_lower, country, tld).
    """
    failed_cutoff = datetime.now(timezone.utc) - timedelta(days=FRESHNESS_DAYS)

    filters = [
        CollectionJobAS24.status == "failed",
        CollectionJobAS24.created_at >= failed_cutoff,
    ]
    if country:
        filters.append(CollectionJobAS24.country == country.upper())
    if tld:
        filters.append(CollectionJobAS24.tld == tld.lower())

    rows = (
        db.session.query(
            func.lower(CollectionJobAS24.make),
            func.lower(CollectionJobAS24.model),
            CollectionJobAS24.country,
            CollectionJobAS24.tld,
            func.count(CollectionJobAS24.id),
        )
        .filter(*filters)
        .group_by(
            func.lower(CollectionJobAS24.make),
            func.lower(CollectionJobAS24.model),
            CollectionJobAS24.country,
            CollectionJobAS24.tld,
        )
        .having(func.count(CollectionJobAS24.id) >= LOW_DATA_FAIL_THRESHOLD)
        .all()
    )

    return {(mk, md, ctry, t) for mk, md, ctry, t, _ in rows}


def _cancel_low_data_pending_as24(
    low_data: set[tuple[str, str, str, str]],
) -> int:
    """Annule les jobs pending/assigned pour les vehicules AS24 low-data."""
    if not low_data:
        return 0

    cancelled = 0
    for make, model, ctry, t in low_data:
        zombies = CollectionJobAS24.query.filter(
            func.lower(CollectionJobAS24.make) == make,
            func.lower(CollectionJobAS24.model) == model,
            CollectionJobAS24.country == ctry,
            CollectionJobAS24.tld == t,
            CollectionJobAS24.status.in_(("pending", "assigned")),
        ).all()
        for job in zombies:
            job.status = "failed"
            job.attempts = MAX_ATTEMPTS
            cancelled += 1
        if zombies:
            logger.info(
                "AS24: cancelled %d zombie jobs for %s %s (country=%s, tld=%s)",
                len(zombies),
                make,
                model,
                ctry,
                t,
            )

    if cancelled:
        db.session.commit()
    return cancelled


# ---------------------------------------------------------------------------
# Expansion principale
# ---------------------------------------------------------------------------


def expand_collection_jobs_as24(
    make: str,
    model: str,
    year: int,
    region: str,
    fuel: str | None = None,
    gearbox: str | None = None,
    hp_range: str | None = None,
    country: str = "CH",
    tld: str = "ch",
    slug_make: str = "",
    slug_model: str = "",
) -> list[CollectionJobAS24]:
    """Expand un vehicule scanne sur AS24 en jobs de collecte (variantes x regions).

    Priorites :
    - P1 : meme vehicule x N-1 autres regions (CH=25 cantons, autres=national)
    - P2 : variante carburant (diesel<->essence) x toutes regions
    - P3 : variante boite (si renseignee) x toutes regions
    - P4 : annee +/-1 x region courante seulement (2 jobs)

    Retourne uniquement les jobs nouvellement crees.
    """
    make = make.strip()
    model = model.strip()
    region = region.strip()
    country = country.upper().strip()
    tld = tld.lower().strip()
    if fuel:
        fuel = fuel.strip().lower()
    if gearbox:
        gearbox = gearbox.strip().lower()

    # Pas de slugs = impossible de construire les URLs AS24
    if not slug_make or not slug_model:
        logger.warning(
            "AS24 expand: slugs manquants pour %s %s, skip expansion",
            make,
            model,
        )
        return []

    # Skip si ce vehicule est low-data
    low_data = _get_low_data_vehicles_as24(country=country, tld=tld)
    if (make.strip().lower(), model.strip().lower(), country, tld) in low_data:
        logger.info(
            "AS24: skipping expansion for low-data %s %s (country=%s, tld=%s)",
            make,
            model,
            country,
            tld,
        )
        return []

    # Cache cooldown
    cache_key = market_text_key(f"{make}:{model}:{year}:{country}:{tld}")
    now_mono = time.monotonic()
    if cache_key in _expand_cache:
        if now_mono - _expand_cache[cache_key] < _EXPAND_COOLDOWN_SECONDS:
            return []
    _expand_cache[cache_key] = now_mono

    source_vehicle = f"{make} {model} {year} {fuel or ''} {gearbox or ''}".strip()
    created: list[CollectionJobAS24] = []

    current_region_key = market_text_key(region)
    all_regions = _get_regions_for_country_as24(country)

    # --- P1 : meme vehicule, N-1 autres regions ---
    for r in all_regions:
        if market_text_key(r) == current_region_key:
            continue
        job = _try_create_job_as24(
            make,
            model,
            year,
            r,
            fuel,
            gearbox,
            hp_range,
            priority=1,
            source_vehicle=source_vehicle,
            country=country,
            tld=tld,
            slug_make=slug_make,
            slug_model=slug_model,
            search_strategy=_get_search_strategy(country, r),
        )
        if job:
            created.append(job)

    # --- P2 : variante carburant (diesel <-> essence) ---
    opposite_fuel = FUEL_OPPOSITES.get(fuel) if fuel else None
    if opposite_fuel:
        for r in all_regions:
            job = _try_create_job_as24(
                make,
                model,
                year,
                r,
                opposite_fuel,
                gearbox,
                None,
                priority=2,
                source_vehicle=source_vehicle,
                country=country,
                tld=tld,
                slug_make=slug_make,
                slug_model=slug_model,
                search_strategy=_get_search_strategy(country, r),
            )
            if job:
                created.append(job)

    # --- P3 : variante boite (si renseignee) ---
    opposite_gearbox = GEARBOX_OPPOSITES.get(gearbox) if gearbox else None
    if opposite_gearbox:
        for r in all_regions:
            job = _try_create_job_as24(
                make,
                model,
                year,
                r,
                fuel,
                opposite_gearbox,
                hp_range,
                priority=3,
                source_vehicle=source_vehicle,
                country=country,
                tld=tld,
                slug_make=slug_make,
                slug_model=slug_model,
                search_strategy=_get_search_strategy(country, r),
            )
            if job:
                created.append(job)

    # --- P4 : annee +/-1 x region courante seulement ---
    for y in [year - 1, year + 1]:
        job = _try_create_job_as24(
            make,
            model,
            y,
            region,
            fuel,
            gearbox,
            hp_range,
            priority=4,
            source_vehicle=source_vehicle,
            country=country,
            tld=tld,
            slug_make=slug_make,
            slug_model=slug_model,
        )
        if job:
            created.append(job)

    db.session.commit()

    logger.info(
        "AS24: expanded %d collection jobs for %s (source: %s, tld=%s)",
        len(created),
        source_vehicle,
        region,
        tld,
    )
    return created


# ---------------------------------------------------------------------------
# Pick & Mark (existants)
# ---------------------------------------------------------------------------


def _reclaim_stale_jobs_as24() -> int:
    """Remet en pending les jobs assigned depuis trop longtemps."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=ASSIGNMENT_TIMEOUT_MINUTES)
    stale = CollectionJobAS24.query.filter(
        CollectionJobAS24.status == "assigned",
        CollectionJobAS24.assigned_at < cutoff,
    ).all()
    for job in stale:
        job.status = "pending"
        job.assigned_at = None
    if stale:
        db.session.commit()
        logger.info("AS24: reclaimed %d stale jobs", len(stale))
    return len(stale)


def pick_bonus_jobs_as24(country: str, tld: str, max_jobs: int = 3) -> list[CollectionJobAS24]:
    """Selectionne les N jobs AS24 pending pour le bon pays/tld."""
    _reclaim_stale_jobs_as24()

    # Detecter et annuler les vehicules low-data
    low_data = _get_low_data_vehicles_as24(country=country, tld=tld)
    _cancel_low_data_pending_as24(low_data)

    jobs = (
        CollectionJobAS24.query.filter(
            CollectionJobAS24.status == "pending",
            CollectionJobAS24.country == country.upper(),
            CollectionJobAS24.tld == tld.lower(),
        )
        .order_by(CollectionJobAS24.priority.asc(), CollectionJobAS24.created_at.asc())
        .limit(max_jobs)
        .all()
    )

    now = datetime.now(timezone.utc)
    for job in jobs:
        job.status = "assigned"
        job.assigned_at = now
    if jobs:
        db.session.commit()
    return jobs


def mark_job_done_as24(job_id: int, success: bool = True) -> None:
    """Marque un job AS24 comme done ou failed."""
    job = db.session.get(CollectionJobAS24, job_id)
    if job is None:
        raise ValueError(f"AS24 Job {job_id} not found")
    if success:
        job.status = "done"
        job.completed_at = datetime.now(timezone.utc)
    else:
        job.attempts += 1
        if job.attempts >= MAX_ATTEMPTS:
            job.status = "failed"
        else:
            job.status = "pending"
    db.session.commit()
