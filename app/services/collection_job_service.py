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

# Mapping pays → liste de regions pour l'expansion des jobs
_COUNTRY_REGIONS: dict[str, list[str]] = {
    "FR": POST_2016_REGIONS,
    "CH": SWISS_CANTONS,
}


def _get_regions_for_country(country: str) -> list[str]:
    """Retourne la liste de regions pour un pays (FR=regions, CH=cantons)."""
    return _COUNTRY_REGIONS.get(country, POST_2016_REGIONS)


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
    country: str = "FR",
) -> bool:
    """Verifie si un MarketPrice frais (< FRESHNESS_DAYS) existe deja."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=FRESHNESS_DAYS)

    filters = [
        market_text_key_expr(MarketPrice.make) == market_text_key(make),
        market_text_key_expr(MarketPrice.model) == market_text_key(model),
        MarketPrice.year == year,
        market_text_key_expr(MarketPrice.region) == market_text_key(region),
        func.coalesce(MarketPrice.country, "FR") == country,
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
    country: str = "FR",
) -> bool:
    """Verifie si un CollectionJob identique existe deja (actif OU failed recent).

    Utilise func.lower() pour make/model (ASCII) et comparaison exacte
    pour region (vient de POST_2016_REGIONS), fuel/gearbox (deja normalises).
    SQLite LOWER() ne gere pas les accents Unicode (Î, Ô, etc.),
    donc on evite func.lower() sur les colonnes avec accents.

    Bloque la creation si :
    - un job pending/assigned existe, OU
    - un job failed existe et a ete cree dans les FRESHNESS_DAYS derniers jours.
    Un failed > FRESHNESS_DAYS sera recree (le marche peut changer).
    """
    failed_cutoff = datetime.now(timezone.utc) - timedelta(days=FRESHNESS_DAYS)

    filters = [
        func.lower(CollectionJob.make) == make.strip().lower(),
        func.lower(CollectionJob.model) == model.strip().lower(),
        CollectionJob.year == year,
        CollectionJob.region == region,  # exact match (from POST_2016_REGIONS)
        db.or_(
            CollectionJob.status.in_(("pending", "assigned")),
            db.and_(
                CollectionJob.status == "failed",
                CollectionJob.created_at >= failed_cutoff,
            ),
        ),
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

    filters.append(func.coalesce(CollectionJob.country, "FR") == country)

    return db.session.query(CollectionJob.id).filter(*filters).first() is not None


def _find_old_failed_job(
    make: str,
    model: str,
    year: int,
    region: str,
    fuel: str | None,
    gearbox: str | None,
    hp_range: str | None,
    country: str = "FR",
) -> CollectionJob | None:
    """Cherche un job failed ancien (> FRESHNESS_DAYS) pour le recycler."""
    failed_cutoff = datetime.now(timezone.utc) - timedelta(days=FRESHNESS_DAYS)

    filters = [
        func.lower(CollectionJob.make) == make.strip().lower(),
        func.lower(CollectionJob.model) == model.strip().lower(),
        CollectionJob.year == year,
        CollectionJob.region == region,
        CollectionJob.status == "failed",
        CollectionJob.created_at < failed_cutoff,
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

    filters.append(func.coalesce(CollectionJob.country, "FR") == country)

    return CollectionJob.query.filter(*filters).first()


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
    country: str = "FR",
) -> CollectionJob | None:
    """Tente de creer un CollectionJob. Retourne None si doublon ou deja frais.

    Si un vieux job failed existe (> FRESHNESS_DAYS), le reinitialise
    au lieu d'en creer un nouveau (UniqueConstraint).
    """
    if _has_fresh_market_price(make, model, year, region, fuel, hp_range, country=country):
        return None

    if _job_exists(make, model, year, region, fuel, gearbox, hp_range, country=country):
        return None

    # Recycler un vieux job failed (la UniqueConstraint empeche un INSERT)
    old = _find_old_failed_job(make, model, year, region, fuel, gearbox, hp_range, country=country)
    if old:
        old.status = "pending"
        old.priority = priority
        old.attempts = 0
        old.assigned_at = None
        old.completed_at = None
        old.created_at = datetime.now(timezone.utc)
        old.source_vehicle = source_vehicle
        return old

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
        country=country,
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
    country: str | None = None,
) -> list[CollectionJob]:
    """Expand un vehicule scanne en jobs de collecte (variantes x regions).

    Priorites :
    - P1 : meme vehicule x N-1 autres regions (13 FR, 26 cantons CH)
    - P2 : variante carburant (diesel/essence seulement) x N regions
    - P3 : variante boite (si renseignee) x N regions
    - P4 : annee +/-1 x region courante seulement (2 jobs)

    Retourne uniquement les jobs nouvellement crees.
    """
    # Normaliser les inputs
    make = make.strip()
    model = model.strip()
    region = region.strip()
    country = (country or "FR").upper().strip()
    if fuel:
        fuel = fuel.strip().lower()
    if gearbox:
        gearbox = gearbox.strip().lower()

    # Skip si ce vehicule est low-data (trop de fails recents)
    low_data = _get_low_data_vehicles(country)
    if (make.strip().lower(), model.strip().lower(), country) in low_data:
        logger.info(
            "Skipping expansion for low-data vehicle %s %s (country=%s)",
            make,
            model,
            country,
        )
        return []

    # Cache : skip si deja expanded recemment (evite ~128 queries par appel)
    # Inclut country pour eviter collision FR/CH sur le meme vehicule
    cache_key = market_text_key(f"{make}:{model}:{year}:{country}")
    now_mono = time.monotonic()
    if cache_key in _expand_cache:
        if now_mono - _expand_cache[cache_key] < _EXPAND_COOLDOWN_SECONDS:
            return []
    _expand_cache[cache_key] = now_mono

    source_vehicle = f"{make} {model} {year} {fuel or ''} {gearbox or ''}".strip()
    created: list[CollectionJob] = []

    current_region_key = market_text_key(region)

    # Selectionner la liste de regions selon le pays
    all_regions = _get_regions_for_country(country)

    # --- P1 : meme vehicule, N-1 autres regions ---
    for r in all_regions:
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
            country=country,
        )
        if job:
            created.append(job)

    # --- P2 : variante carburant (diesel <-> essence seulement) ---
    opposite_fuel = FUEL_OPPOSITES.get(fuel) if fuel else None

    if opposite_fuel:
        for r in all_regions:
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
                country=country,
            )
            if job:
                created.append(job)

    # --- P3 : variante boite (si renseignee) ---
    opposite_gearbox = GEARBOX_OPPOSITES.get(gearbox) if gearbox else None

    if opposite_gearbox:
        for r in all_regions:
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
                country=country,
            )
            if job:
                created.append(job)

    # --- P4 : annee +/-1 x region courante seulement ---
    # Limite a la region courante pour eviter l'explosion de la queue (2 jobs).
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
            country=country,
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


LOW_DATA_FAIL_THRESHOLD = 3


def _get_low_data_vehicles(country: str | None = None) -> set[tuple[str, str, str]]:
    """Identifie les vehicules (make, model, country) avec >= LOW_DATA_FAIL_THRESHOLD jobs failed recents.

    Groupe par (make, model, country) pour eviter que les echecs d'un pays
    contaminent un autre. Si country est fourni, ne retourne que ce pays.
    """
    failed_cutoff = datetime.now(timezone.utc) - timedelta(days=FRESHNESS_DAYS)

    filters = [
        CollectionJob.status == "failed",
        CollectionJob.created_at >= failed_cutoff,
    ]
    if country:
        filters.append(func.coalesce(CollectionJob.country, "FR") == country)

    rows = (
        db.session.query(
            func.lower(CollectionJob.make),
            func.lower(CollectionJob.model),
            func.coalesce(CollectionJob.country, "FR"),
            func.count(CollectionJob.id),
        )
        .filter(*filters)
        .group_by(
            func.lower(CollectionJob.make),
            func.lower(CollectionJob.model),
            func.coalesce(CollectionJob.country, "FR"),
        )
        .having(func.count(CollectionJob.id) >= LOW_DATA_FAIL_THRESHOLD)
        .all()
    )

    return {(make, model, ctry) for make, model, ctry, _ in rows}


def _cancel_low_data_pending(low_data: set[tuple[str, str, str]]) -> int:
    """Annule (status=failed) tous les jobs pending/assigned pour les vehicules low-data.

    Filtre par (make, model, country) pour ne pas annuler les jobs d'un autre pays.
    Evite que des dizaines de jobs P2/P3/P4 restent en queue et soient
    re-selectionnes sans fin quand le vehicule est manifestement introuvable.
    """
    if not low_data:
        return 0

    cancelled = 0
    for make, model, ctry in low_data:
        zombies = CollectionJob.query.filter(
            func.lower(CollectionJob.make) == make,
            func.lower(CollectionJob.model) == model,
            CollectionJob.status.in_(("pending", "assigned")),
            func.coalesce(CollectionJob.country, "FR") == ctry,
        ).all()
        for job in zombies:
            job.status = "failed"
            job.attempts = MAX_ATTEMPTS
            cancelled += 1
        if zombies:
            logger.info(
                "Cancelled %d zombie jobs for low-data vehicle %s %s (country=%s)",
                len(zombies),
                make,
                model,
                ctry,
            )

    if cancelled:
        db.session.commit()
    return cancelled


def pick_bonus_jobs(max_jobs: int = 3) -> list[CollectionJob]:
    """Selectionne les N jobs pending les plus prioritaires et les assigne.

    Reclame d'abord les jobs stale (assigned > 30 min).
    Annule les jobs des vehicules low-data (>= LOW_DATA_FAIL_THRESHOLD fails recents).
    ORDER BY priority ASC (P1 d'abord), created_at ASC (FIFO).
    """
    _reclaim_stale_jobs()

    # Detecter les vehicules low-data (tous pays) et annuler leurs jobs
    low_data = _get_low_data_vehicles(country=None)
    _cancel_low_data_pending(low_data)

    query = CollectionJob.query.filter(CollectionJob.status == "pending").order_by(
        CollectionJob.priority.asc(), CollectionJob.created_at.asc()
    )

    jobs = query.limit(max_jobs).all()

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
