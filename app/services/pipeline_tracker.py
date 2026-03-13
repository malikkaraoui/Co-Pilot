"""Utilitaire de suivi des executions de pipeline.

Chaque pipeline (import CSV, collecte marche, enrichissement, etc.) est trace
dans la table PipelineRun. Ce module fournit un context manager pour simplifier
le tracking : on entre avec status "running", on sort avec "success" ou "failure".

Ca permet de monitorer en admin quels pipelines tournent, lesquels ont plante,
et combien d'elements ont ete traites.
"""

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
    # On persiste tout de suite pour que le run soit visible en admin
    # meme si le pipeline est encore en cours
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
        # On catch les erreurs "metier" mais pas SystemExit / KeyboardInterrupt
        run.status = "failure"
        run.error_message = f"{type(exc).__name__}: {exc}"
        run.finished_at = datetime.now(timezone.utc)
        db.session.commit()
        logger.error("Pipeline '%s' echoue: %s", name, exc)
        raise
