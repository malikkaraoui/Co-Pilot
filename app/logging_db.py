"""DBHandler -- persiste les WARNING/ERROR dans la table app_logs.

Permet de consulter les erreurs recentes directement depuis le dashboard
admin sans avoir a fouiller dans les logs Render. Les logs INFO et DEBUG
ne sont pas persistes pour eviter de gonfler la DB inutilement.
"""

import logging
import sys
from datetime import datetime, timezone

from flask import has_app_context
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models.log import AppLog

logger = logging.getLogger(__name__)

# Attributs standard d'un LogRecord -- on les exclut du champ 'extra'
# pour ne stocker que les attributs custom ajoutes par le code metier
# (ex: logger.warning("truc", extra={"vin": "ABC123"}))
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

    Quelques subtilites :
    - Thread-safe : logging.Handler.handle() acquiert self.lock avant emit(),
      donc pas besoin de lock supplementaire.
    - Flask-SQLAlchemy utilise des sessions scoped (thread-local), donc
      chaque thread a sa propre session — pas de conflit.
    - Si pas de contexte Flask (ex: thread du ThreadPoolExecutor),
      on pousse le contexte manuellement via self._app.
    - Si l'ecriture DB echoue, on print sur stderr et on continue.
      Un handler de log ne doit jamais faire planter l'app.
    """

    def __init__(self, app=None, level=logging.WARNING):
        super().__init__(level)
        # On garde une ref a l'app pour pouvoir pousser un app_context
        # depuis des threads sans contexte Flask
        self._app = app

    def emit(self, record: logging.LogRecord) -> None:
        """Persiste un log record dans la table app_logs."""
        # Garde anti-recursion : si on loggue depuis ce module ou depuis
        # SQLAlchemy, on skip pour eviter une boucle infinie
        # (log -> DB write -> SQLAlchemy log -> DB write -> ...)
        if record.name == "app.logging_db" or record.name.startswith("sqlalchemy"):
            return

        if not has_app_context() and self._app is None:
            return

        try:
            if has_app_context():
                self._write(record)
            else:
                # Hors contexte Flask (thread worker) — on en cree un
                with self._app.app_context():
                    self._write(record)
        except (OSError, ValueError, TypeError, RuntimeError, SQLAlchemyError) as exc:
            # Un handler de log ne doit JAMAIS lever d'exception,
            # sinon ca masque l'erreur originale
            print(f"DBHandler.emit failed: {exc}", file=sys.stderr)
            try:
                db.session.rollback()
            except (OSError, RuntimeError, SQLAlchemyError):
                pass

    def _write(self, record: logging.LogRecord) -> None:
        """Ecrit le record en base (doit etre appele dans un app context).

        Extrait les attributs non-standard du LogRecord pour les stocker
        dans le champ JSON 'extra' — ca permet de retrouver le contexte
        metier (VIN, annonce_id, etc.) directement dans le dashboard.
        """
        # On filtre les attributs standard et prives pour ne garder
        # que ce que le code metier a ajoute via extra={}
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
