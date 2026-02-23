"""Service CollectionJob -- expansion et gestion de la file d'attente argus."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.collection_job import CollectionJob
from app.models.market_price import MarketPrice
from app.services.market_service import market_text_key, market_text_key_expr

logger = logging.getLogger(__name__)

FRESHNESS_DAYS = 7
MAX_ATTEMPTS = 3

POST_2016_REGIONS = [
    "Île-de-France",
    "Auvergne-Rhône-Alpes",
    "Provence-Alpes-Côte d'Azur",
    "Occitanie",
    "Nouvelle-Aquitaine",
    "Hauts-de-France",
    "Grand Est",
    "Bretagne",
    "Pays de la Loire",
    "Normandie",
    "Bourgogne-Franche-Comté",
    "Centre-Val de Loire",
    "Corse",
]

FUEL_OPPOSITES = {"diesel": "essence", "essence": "diesel"}
GEARBOX_OPPOSITES = {
    "manual": "automatique",
    "manuelle": "automatique",
    "automatique": "manuelle",
    "auto": "manuelle",
}


def _has_fresh_market_price(
    make: str,
    model: str,
    year: int,
    region: str,
    fuel: str | None,
    hp_range: str | None,
) -> bool:
    """Verifie si un MarketPrice frais (< FRESHNESS_DAYS) existe deja."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=FRESHNESS_DAYS)

    filters = [
        market_text_key_expr(MarketPrice.make) == market_text_key(make),
        market_text_key_expr(MarketPrice.model) == market_text_key(model),
        MarketPrice.year == year,
        market_text_key_expr(MarketPrice.region) == market_text_key(region),
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


def _job_exists(
    make: str,
    model: str,
    year: int,
    region: str,
    fuel: str | None,
    gearbox: str | None,
    hp_range: str | None,
) -> bool:
    """Verifie si un CollectionJob identique existe deja.

    Necessaire car SQLite considere NULL != NULL dans les UNIQUE constraints,
    ce qui permet des doublons quand fuel, gearbox ou hp_range est None.
    """
    filters = [
        CollectionJob.make == make,
        CollectionJob.model == model,
        CollectionJob.year == year,
        CollectionJob.region == region,
    ]

    for col, val in [
        (CollectionJob.fuel, fuel),
        (CollectionJob.gearbox, gearbox),
        (CollectionJob.hp_range, hp_range),
    ]:
        if val is None:
            filters.append(col.is_(None))
        else:
            filters.append(col == val)

    return db.session.query(CollectionJob.id).filter(*filters).first() is not None


def _try_create_job(
    make: str,
    model: str,
    year: int,
    region: str,
    fuel: str | None,
    gearbox: str | None,
    hp_range: str | None,
    priority: int,
    source_vehicle: str,
) -> CollectionJob | None:
    """Tente de creer un CollectionJob. Retourne None si doublon ou deja frais."""
    if _has_fresh_market_price(make, model, year, region, fuel, hp_range):
        return None

    if _job_exists(make, model, year, region, fuel, gearbox, hp_range):
        return None

    job = CollectionJob(
        make=make,
        model=model,
        year=year,
        region=region,
        fuel=fuel,
        gearbox=gearbox,
        hp_range=hp_range,
        priority=priority,
        source_vehicle=source_vehicle,
    )

    # Utilise un savepoint (nested transaction) pour que le rollback
    # en cas de doublon n'annule pas les autres jobs deja crees.
    nested = db.session.begin_nested()
    try:
        db.session.add(job)
        nested.commit()
    except IntegrityError:
        nested.rollback()
        return None

    return job


def expand_collection_jobs(
    make: str,
    model: str,
    year: int,
    region: str,
    fuel: str | None = None,
    gearbox: str | None = None,
    hp_range: str | None = None,
) -> list[CollectionJob]:
    """Expand un vehicule scanne en jobs de collecte (variantes x regions).

    Priorites :
    - P1 : meme vehicule x 12 autres regions
    - P2 : variante carburant (diesel/essence seulement) x 13 regions
    - P3 : variante boite (si renseignee) x 13 regions
    - P4 : annee +/-1 x 13 regions

    Retourne uniquement les jobs nouvellement crees.
    """
    source_vehicle = f"{make} {model} {year} {fuel or ''} {gearbox or ''}".strip()
    created: list[CollectionJob] = []

    current_region_key = market_text_key(region)

    # --- P1 : meme vehicule, 12 autres regions ---
    for r in POST_2016_REGIONS:
        if market_text_key(r) == current_region_key:
            continue
        job = _try_create_job(
            make,
            model,
            year,
            r,
            fuel,
            gearbox,
            hp_range,
            priority=1,
            source_vehicle=source_vehicle,
        )
        if job:
            created.append(job)

    # --- P2 : variante carburant (diesel <-> essence seulement) ---
    fuel_lower = fuel.lower() if fuel else None
    opposite_fuel = FUEL_OPPOSITES.get(fuel_lower) if fuel_lower else None

    if opposite_fuel:
        for r in POST_2016_REGIONS:
            job = _try_create_job(
                make,
                model,
                year,
                r,
                opposite_fuel,
                gearbox,
                None,
                priority=2,
                source_vehicle=source_vehicle,
            )
            if job:
                created.append(job)

    # --- P3 : variante boite (si renseignee) ---
    gearbox_lower = gearbox.lower() if gearbox else None
    opposite_gearbox = GEARBOX_OPPOSITES.get(gearbox_lower) if gearbox_lower else None

    if opposite_gearbox:
        for r in POST_2016_REGIONS:
            job = _try_create_job(
                make,
                model,
                year,
                r,
                fuel,
                opposite_gearbox,
                hp_range,
                priority=3,
                source_vehicle=source_vehicle,
            )
            if job:
                created.append(job)

    # --- P4 : annee +/-1 x 13 regions ---
    for y in [year - 1, year + 1]:
        for r in POST_2016_REGIONS:
            job = _try_create_job(
                make,
                model,
                y,
                r,
                fuel,
                gearbox,
                hp_range,
                priority=4,
                source_vehicle=source_vehicle,
            )
            if job:
                created.append(job)

    db.session.commit()

    logger.info(
        "Expanded %d collection jobs for %s (source: %s)",
        len(created),
        source_vehicle,
        region,
    )
    return created


def pick_bonus_jobs(max_jobs: int = 3) -> list[CollectionJob]:
    """Selectionne les N jobs pending les plus prioritaires et les assigne.

    ORDER BY priority ASC (P1 d'abord), created_at ASC (FIFO).
    """
    jobs = (
        CollectionJob.query.filter(CollectionJob.status == "pending")
        .order_by(CollectionJob.priority.asc(), CollectionJob.created_at.asc())
        .limit(max_jobs)
        .all()
    )

    now = datetime.now(timezone.utc)
    for job in jobs:
        job.status = "assigned"
        job.assigned_at = now

    db.session.commit()
    return jobs


def mark_job_done(job_id: int, success: bool = True) -> None:
    """Marque un job comme done ou failed.

    En cas d'echec, reinitialise en pending si attempts < MAX_ATTEMPTS
    pour permettre un retry automatique.
    """
    job = db.session.get(CollectionJob, job_id)
    if job is None:
        raise ValueError(f"Job {job_id} not found")

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
