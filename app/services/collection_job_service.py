"""Service CollectionJob -- expansion et gestion de la file d'attente argus."""

import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.collection_job import CollectionJob
from app.models.market_price import MarketPrice
from app.services.market_service import market_text_key, market_text_key_expr

logger = logging.getLogger(__name__)

FRESHNESS_DAYS = 7
MAX_ATTEMPTS = 3
ASSIGNMENT_TIMEOUT_MINUTES = 30

# Cache en memoire pour eviter de re-expand le meme vehicule a chaque requete.
# Cle: "make:model:year" normalise, valeur: timestamp de derniere expansion.
_expand_cache: dict[str, float] = {}
_EXPAND_COOLDOWN_SECONDS = 300  # 5 minutes

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
    """Verifie si un CollectionJob actif identique existe deja.

    Utilise func.lower() pour make/model (ASCII) et comparaison exacte
    pour region (vient de POST_2016_REGIONS), fuel/gearbox (deja normalises).
    SQLite LOWER() ne gere pas les accents Unicode (Î, Ô, etc.),
    donc on evite func.lower() sur les colonnes avec accents.
    Ne cherche que les jobs pending/assigned (les done/failed ne bloquent pas).
    """
    filters = [
        func.lower(CollectionJob.make) == make.strip().lower(),
        func.lower(CollectionJob.model) == model.strip().lower(),
        CollectionJob.year == year,
        CollectionJob.region == region,  # exact match (from POST_2016_REGIONS)
        CollectionJob.status.in_(("pending", "assigned")),
    ]

    for col, val in [
        (CollectionJob.fuel, fuel),
        (CollectionJob.gearbox, gearbox),
        (CollectionJob.hp_range, hp_range),
    ]:
        if val is None:
            filters.append(col.is_(None))
        else:
            filters.append(col == val)  # already normalized in expand()

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
    - P4 : annee +/-1 x region courante seulement (2 jobs, pas 26)

    Retourne uniquement les jobs nouvellement crees.
    """
    # Normaliser les inputs
    make = make.strip()
    model = model.strip()
    region = region.strip()
    if fuel:
        fuel = fuel.strip().lower()
    if gearbox:
        gearbox = gearbox.strip().lower()

    # Cache : skip si deja expanded recemment (evite ~128 queries par appel)
    cache_key = market_text_key(f"{make}:{model}:{year}")
    now_mono = time.monotonic()
    if cache_key in _expand_cache:
        if now_mono - _expand_cache[cache_key] < _EXPAND_COOLDOWN_SECONDS:
            return []
    _expand_cache[cache_key] = now_mono

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
    opposite_fuel = FUEL_OPPOSITES.get(fuel) if fuel else None

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
    opposite_gearbox = GEARBOX_OPPOSITES.get(gearbox) if gearbox else None

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

    # --- P4 : annee +/-1 x region courante seulement ---
    # Limite a la region courante pour eviter l'explosion de la queue (2 au lieu de 26).
    # Les autres regions pour les annees adjacentes seront generees quand un utilisateur
    # scannera un vehicule de cette annee dans cette region.
    for y in [year - 1, year + 1]:
        job = _try_create_job(
            make,
            model,
            y,
            region,
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


def _reclaim_stale_jobs() -> int:
    """Remet en pending les jobs assigned depuis plus de ASSIGNMENT_TIMEOUT_MINUTES.

    Evite que des jobs restent bloques en 'assigned' si l'extension crash
    ou ne callback jamais.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=ASSIGNMENT_TIMEOUT_MINUTES)
    stale = CollectionJob.query.filter(
        CollectionJob.status == "assigned",
        CollectionJob.assigned_at < cutoff,
    ).all()

    for job in stale:
        job.status = "pending"
        job.assigned_at = None

    if stale:
        db.session.commit()
        logger.info("Reclaimed %d stale assigned jobs", len(stale))

    return len(stale)


def pick_bonus_jobs(max_jobs: int = 3) -> list[CollectionJob]:
    """Selectionne les N jobs pending les plus prioritaires et les assigne.

    Reclame d'abord les jobs stale (assigned > 30 min).
    ORDER BY priority ASC (P1 d'abord), created_at ASC (FIFO).
    """
    _reclaim_stale_jobs()

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

    Refuse les jobs qui ne sont pas en status assigned ou pending.
    En cas d'echec, reinitialise en pending si attempts < MAX_ATTEMPTS
    pour permettre un retry automatique.
    """
    job = db.session.get(CollectionJob, job_id)
    if job is None:
        raise ValueError(f"Job {job_id} not found")

    if job.status not in ("assigned", "pending"):
        raise ValueError(
            f"Job {job_id} has status '{job.status}', expected 'assigned' or 'pending'"
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
