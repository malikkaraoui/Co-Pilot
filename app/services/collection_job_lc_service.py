"""Service CollectionJobLacentrale -- file d'attente de collecte pour La Centrale.

Meme pattern que les autres collection_job_*_service, mais simplifie
car La Centrale est toujours national (France) sans granularite regionale
dans l'URL de recherche. L'expansion cree donc des variantes vehicule
(carburant, boite, annee) mais pas des variantes region.
"""

import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.collection_job_lacentrale import CollectionJobLacentrale
from app.models.market_price import MarketPrice
from app.services.market_service import market_text_key, market_text_key_expr

logger = logging.getLogger(__name__)

FRESHNESS_DAYS = 7
MAX_ATTEMPTS = 3
ASSIGNMENT_TIMEOUT_MINUTES = 30
LOW_DATA_FAIL_THRESHOLD = 3

_expand_cache: dict[str, float] = {}
_EXPAND_COOLDOWN_SECONDS = 300  # 5 minutes

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


def _has_fresh_market_price_lc(
    make: str,
    model: str,
    year: int,
    fuel: str | None,
    hp_range: str | None,
) -> bool:
    """Verifie si un MarketPrice frais existe pour ce combo (region=France).

    Toujours region="France" car La Centrale ne supporte pas le filtre region.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=FRESHNESS_DAYS)

    filters = [
        market_text_key_expr(MarketPrice.make) == market_text_key(make),
        market_text_key_expr(MarketPrice.model) == market_text_key(model),
        MarketPrice.year == year,
        market_text_key_expr(MarketPrice.region) == market_text_key("France"),
        func.coalesce(MarketPrice.country, "FR") == "FR",
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


def _job_exists_lc(
    make: str,
    model: str,
    year: int,
    fuel: str | None,
    gearbox: str | None,
    hp_range: str | None,
) -> bool:
    """Verifie si un CollectionJobLacentrale identique existe deja."""
    failed_cutoff = datetime.now(timezone.utc) - timedelta(days=FRESHNESS_DAYS)

    filters = [
        func.lower(CollectionJobLacentrale.make) == make.strip().lower(),
        func.lower(CollectionJobLacentrale.model) == model.strip().lower(),
        CollectionJobLacentrale.year == year,
        CollectionJobLacentrale.region == "France",
        db.or_(
            CollectionJobLacentrale.status.in_(("pending", "assigned")),
            db.and_(
                CollectionJobLacentrale.status == "failed",
                CollectionJobLacentrale.created_at >= failed_cutoff,
            ),
        ),
    ]

    for col, val in [
        (CollectionJobLacentrale.fuel, fuel),
        (CollectionJobLacentrale.gearbox, gearbox),
        (CollectionJobLacentrale.hp_range, hp_range),
    ]:
        if val is None:
            filters.append(col.is_(None))
        else:
            filters.append(col == val)

    return db.session.query(CollectionJobLacentrale.id).filter(*filters).first() is not None


def _find_old_failed_job_lc(
    make: str,
    model: str,
    year: int,
    fuel: str | None,
    gearbox: str | None,
    hp_range: str | None,
) -> CollectionJobLacentrale | None:
    """Cherche un job LC failed ancien pour le recycler."""
    failed_cutoff = datetime.now(timezone.utc) - timedelta(days=FRESHNESS_DAYS)

    filters = [
        func.lower(CollectionJobLacentrale.make) == make.strip().lower(),
        func.lower(CollectionJobLacentrale.model) == model.strip().lower(),
        CollectionJobLacentrale.year == year,
        CollectionJobLacentrale.region == "France",
        CollectionJobLacentrale.status == "failed",
        CollectionJobLacentrale.created_at < failed_cutoff,
    ]

    for col, val in [
        (CollectionJobLacentrale.fuel, fuel),
        (CollectionJobLacentrale.gearbox, gearbox),
        (CollectionJobLacentrale.hp_range, hp_range),
    ]:
        if val is None:
            filters.append(col.is_(None))
        else:
            filters.append(col == val)

    return CollectionJobLacentrale.query.filter(*filters).first()


def _try_create_job_lc(
    make: str,
    model: str,
    year: int,
    fuel: str | None,
    gearbox: str | None,
    hp_range: str | None,
    priority: int,
    source_vehicle: str,
) -> CollectionJobLacentrale | None:
    """Tente de creer un CollectionJobLacentrale. Retourne None si doublon ou frais."""
    if _has_fresh_market_price_lc(make, model, year, fuel, hp_range):
        return None

    if _job_exists_lc(make, model, year, fuel, gearbox, hp_range):
        return None

    # Recycler un vieux job failed si possible
    old = _find_old_failed_job_lc(make, model, year, fuel, gearbox, hp_range)
    if old:
        old.status = "pending"
        old.priority = priority
        old.attempts = 0
        old.assigned_at = None
        old.completed_at = None
        old.created_at = datetime.now(timezone.utc)
        old.source_vehicle = source_vehicle
        return old

    job = CollectionJobLacentrale(
        make=make,
        model=model,
        year=year,
        region="France",
        fuel=fuel,
        gearbox=gearbox,
        hp_range=hp_range,
        priority=priority,
        source_vehicle=source_vehicle,
        country="FR",
    )

    # Savepoint pour isoler l'IntegrityError
    nested = db.session.begin_nested()
    try:
        db.session.add(job)
        nested.commit()
    except IntegrityError:
        nested.rollback()
        return None

    return job


# ---------------------------------------------------------------------------
# Low-data detection
# ---------------------------------------------------------------------------


def _get_low_data_vehicles_lc() -> set[tuple[str, str]]:
    """Identifie les vehicules LC avec >= LOW_DATA_FAIL_THRESHOLD fails recents.

    Retourne un set de (make_lower, model_lower).
    Pas de filtre pays/tld ici car LC = toujours France.
    """
    failed_cutoff = datetime.now(timezone.utc) - timedelta(days=FRESHNESS_DAYS)

    rows = (
        db.session.query(
            func.lower(CollectionJobLacentrale.make),
            func.lower(CollectionJobLacentrale.model),
            func.count(CollectionJobLacentrale.id),
        )
        .filter(
            CollectionJobLacentrale.status == "failed",
            CollectionJobLacentrale.created_at >= failed_cutoff,
        )
        .group_by(
            func.lower(CollectionJobLacentrale.make),
            func.lower(CollectionJobLacentrale.model),
        )
        .having(func.count(CollectionJobLacentrale.id) >= LOW_DATA_FAIL_THRESHOLD)
        .all()
    )

    return {(mk, md) for mk, md, _ in rows}


def _cancel_low_data_pending_lc(low_data: set[tuple[str, str]]) -> int:
    """Annule les jobs pending/assigned pour les vehicules LC low-data."""
    if not low_data:
        return 0

    cancelled = 0
    for make, model in low_data:
        zombies = CollectionJobLacentrale.query.filter(
            func.lower(CollectionJobLacentrale.make) == make,
            func.lower(CollectionJobLacentrale.model) == model,
            CollectionJobLacentrale.status.in_(("pending", "assigned")),
        ).all()
        for job in zombies:
            job.status = "failed"
            job.attempts = MAX_ATTEMPTS
            cancelled += 1
        if zombies:
            logger.info(
                "LC: cancelled %d zombie jobs for %s %s",
                len(zombies),
                make,
                model,
            )

    if cancelled:
        db.session.commit()
    return cancelled


# ---------------------------------------------------------------------------
# Expansion principale
# ---------------------------------------------------------------------------


def expand_collection_jobs_lc(
    make: str,
    model: str,
    year: int,
    fuel: str | None = None,
    gearbox: str | None = None,
    hp_range: str | None = None,
) -> list[CollectionJobLacentrale]:
    """Expand un vehicule scanne sur La Centrale en jobs de collecte.

    LC est national (pas de region dans l'URL de recherche), donc
    l'expansion cree des variantes vehicule, pas des variantes region :
    - P1 : variante carburant (diesel <-> essence)
    - P2 : variante boite (si renseignee)
    - P3 : annee +/-1
    """
    make = make.strip()
    model = model.strip()
    if fuel:
        fuel = fuel.strip().lower()
    if gearbox:
        gearbox = gearbox.strip().lower()

    # Skip si le vehicule est low-data
    low_data = _get_low_data_vehicles_lc()
    if (make.strip().lower(), model.strip().lower()) in low_data:
        logger.info("LC: skipping expansion for low-data %s %s", make, model)
        return []

    # Cache cooldown
    cache_key = market_text_key(f"lc:{make}:{model}:{year}")
    now_mono = time.monotonic()
    if cache_key in _expand_cache:
        if now_mono - _expand_cache[cache_key] < _EXPAND_COOLDOWN_SECONDS:
            return []
    _expand_cache[cache_key] = now_mono

    source_vehicle = f"{make} {model} {year} {fuel or ''} {gearbox or ''}".strip()
    created: list[CollectionJobLacentrale] = []

    # --- P1 : variante carburant (diesel <-> essence) ---
    opposite_fuel = FUEL_OPPOSITES.get(fuel) if fuel else None
    if opposite_fuel:
        job = _try_create_job_lc(
            make,
            model,
            year,
            opposite_fuel,
            gearbox,
            None,
            priority=1,
            source_vehicle=source_vehicle,
        )
        if job:
            created.append(job)

    # --- P2 : variante boite (si renseignee) ---
    opposite_gearbox = GEARBOX_OPPOSITES.get(gearbox) if gearbox else None
    if opposite_gearbox:
        job = _try_create_job_lc(
            make,
            model,
            year,
            fuel,
            opposite_gearbox,
            hp_range,
            priority=2,
            source_vehicle=source_vehicle,
        )
        if job:
            created.append(job)

    # --- P3 : annee +/-1 ---
    for y in [year - 1, year + 1]:
        job = _try_create_job_lc(
            make,
            model,
            y,
            fuel,
            gearbox,
            hp_range,
            priority=3,
            source_vehicle=source_vehicle,
        )
        if job:
            created.append(job)

    db.session.commit()

    logger.info(
        "LC: expanded %d collection jobs for %s",
        len(created),
        source_vehicle,
    )
    return created


# ---------------------------------------------------------------------------
# Pick & Mark
# ---------------------------------------------------------------------------


def _reclaim_stale_jobs_lc() -> int:
    """Remet en pending les jobs LC assigned depuis trop longtemps."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=ASSIGNMENT_TIMEOUT_MINUTES)
    stale = CollectionJobLacentrale.query.filter(
        CollectionJobLacentrale.status == "assigned",
        CollectionJobLacentrale.assigned_at < cutoff,
    ).all()
    for job in stale:
        job.status = "pending"
        job.assigned_at = None
    if stale:
        db.session.commit()
        logger.info("LC: reclaimed %d stale jobs", len(stale))
    return len(stale)


def pick_bonus_jobs_lc(max_jobs: int = 3) -> list[CollectionJobLacentrale]:
    """Selectionne les N jobs LC pending les plus prioritaires.

    Pas de filtre pays/tld ici car LC = toujours France.
    """
    _reclaim_stale_jobs_lc()

    low_data = _get_low_data_vehicles_lc()
    _cancel_low_data_pending_lc(low_data)

    jobs = (
        CollectionJobLacentrale.query.filter(
            CollectionJobLacentrale.status == "pending",
        )
        .order_by(
            CollectionJobLacentrale.priority.asc(),
            CollectionJobLacentrale.created_at.asc(),
        )
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


def mark_job_done_lc(job_id: int, success: bool = True) -> None:
    """Marque un job LC comme done ou failed."""
    job = db.session.get(CollectionJobLacentrale, job_id)
    if job is None:
        raise ValueError(f"LC Job {job_id} not found")

    if job.status not in ("assigned", "pending"):
        raise ValueError(
            f"LC Job {job_id} has status '{job.status}', expected 'assigned' or 'pending'"
        )

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
