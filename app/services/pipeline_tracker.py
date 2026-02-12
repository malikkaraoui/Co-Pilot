"""Utilitaire de suivi des executions de pipeline."""

import logging
from contextlib import contextmanager
from datetime import datetime, timezone

from app.extensions import db
from app.models.pipeline_run import PipelineRun

logger = logging.getLogger(__name__)


@contextmanager
def track_pipeline(name: str):
    """Context manager pour tracer l'execution d'un pipeline.

    Usage::

        with track_pipeline("import_csv_specs") as tracker:
            # ... do work ...
            tracker.count = 42

    A la sortie, le PipelineRun est mis a jour avec le status
    et finished_at. En cas d'exception, status='failure' et
    error_message est renseigne.
    """
    run = PipelineRun(
        name=name,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    db.session.add(run)
    db.session.commit()

    try:
        yield run
        run.status = "success"
        run.finished_at = datetime.now(timezone.utc)
        db.session.commit()
        logger.info("Pipeline '%s' termine avec succes (%d elements)", name, run.count or 0)
    except (KeyError, ValueError, AttributeError, TypeError, OSError, IOError) as exc:
        run.status = "failure"
        run.error_message = f"{type(exc).__name__}: {exc}"
        run.finished_at = datetime.now(timezone.utc)
        db.session.commit()
        logger.error("Pipeline '%s' echoue: %s", name, exc)
        raise
