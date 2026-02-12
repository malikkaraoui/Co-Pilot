"""DBHandler -- persiste les WARNING/ERROR dans la table app_logs."""

import logging
import sys
from datetime import datetime, timezone

from flask import has_app_context
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models.log import AppLog

logger = logging.getLogger(__name__)

# Attributs standard d'un LogRecord -- on ne les stocke pas dans 'extra'
_STANDARD_ATTRS = frozenset(
    {
        "name",
        "msg",
        "args",
        "created",
        "relativeCreated",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "pathname",
        "filename",
        "module",
        "levelname",
        "levelno",
        "msecs",
        "message",
        "thread",
        "threadName",
        "process",
        "processName",
        "taskName",
    }
)


class DBHandler(logging.Handler):
    """Logging handler qui ecrit les records WARNING+ dans AppLog.

    Thread-safe : logging.Handler.handle() acquiert self.lock avant emit().
    Flask-SQLAlchemy utilise des sessions scoped (thread-local).

    Si pas de contexte Flask, le record est ignore silencieusement.
    Si l'ecriture DB echoue, l'erreur est imprimee sur stderr sans crash.
    """

    def __init__(self, app=None, level=logging.WARNING):
        super().__init__(level)
        self._app = app

    def emit(self, record: logging.LogRecord) -> None:
        """Persiste un log record dans la table app_logs."""
        # Garde anti-recursion : skip nos propres logs et ceux de SQLAlchemy
        if record.name == "app.logging_db" or record.name.startswith("sqlalchemy"):
            return

        if not has_app_context() and self._app is None:
            return

        try:
            if has_app_context():
                self._write(record)
            else:
                with self._app.app_context():
                    self._write(record)
        except (OSError, ValueError, TypeError, RuntimeError, SQLAlchemyError) as exc:
            print(f"DBHandler.emit failed: {exc}", file=sys.stderr)
            try:
                db.session.rollback()
            except (OSError, RuntimeError, SQLAlchemyError):
                pass

    def _write(self, record: logging.LogRecord) -> None:
        """Ecrit le record en base (doit etre appele dans un app context)."""
        extra = {
            k: v
            for k, v in record.__dict__.items()
            if k not in _STANDARD_ATTRS and not k.startswith("_")
        } or None

        log_entry = AppLog(
            level=record.levelname,
            module=record.name,
            message=self.format(record) if self.formatter else record.getMessage(),
            extra=extra,
            created_at=datetime.fromtimestamp(record.created, tz=timezone.utc),
        )
        db.session.add(log_entry)
        db.session.commit()
