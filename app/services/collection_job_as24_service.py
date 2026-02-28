"""Service CollectionJobAS24 -- gestion de la file d'attente pour AutoScout24."""

import logging
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models.collection_job_as24 import CollectionJobAS24

logger = logging.getLogger(__name__)

FRESHNESS_DAYS = 7
MAX_ATTEMPTS = 3
ASSIGNMENT_TIMEOUT_MINUTES = 30


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
