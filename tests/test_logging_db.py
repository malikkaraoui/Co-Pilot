"""Tests du DBHandler -- journalisation en base de donnees."""

import logging
from unittest.mock import patch

from app.logging_db import DBHandler
from app.models.log import AppLog


class TestDBHandler:
    """Tests du handler de journalisation en base."""

    def _make_handler(self, app):
        """Cree un DBHandler de test attache a un logger isole."""
        return DBHandler(app=app, level=logging.WARNING)

    def test_error_persisted(self, app, db):
        """Un log ERROR est persiste dans app_logs."""
        handler = self._make_handler(app)
        test_logger = logging.getLogger("test.dbhandler.error")
        test_logger.addHandler(handler)
        try:
            with app.app_context():
                test_logger.error("Test error message")

                log = AppLog.query.filter_by(module="test.dbhandler.error").first()
                assert log is not None
                assert log.level == "ERROR"
                assert "Test error message" in log.message
        finally:
            test_logger.removeHandler(handler)

    def test_warning_persisted(self, app, db):
        """Un log WARNING est persiste dans app_logs."""
        handler = self._make_handler(app)
        test_logger = logging.getLogger("test.dbhandler.warning")
        test_logger.addHandler(handler)
        try:
            with app.app_context():
                test_logger.warning("Test warning message")

                log = AppLog.query.filter_by(module="test.dbhandler.warning").first()
                assert log is not None
                assert log.level == "WARNING"
        finally:
            test_logger.removeHandler(handler)

    def test_info_not_persisted(self, app, db):
        """Un log INFO n'est PAS persiste (handler level=WARNING)."""
        handler = self._make_handler(app)
        test_logger = logging.getLogger("test.dbhandler.info")
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.DEBUG)
        try:
            with app.app_context():
                test_logger.info("Should not be persisted")

                log = AppLog.query.filter_by(module="test.dbhandler.info").first()
                assert log is None
        finally:
            test_logger.removeHandler(handler)

    def test_survives_db_failure(self, app, db):
        """Le handler ne crashe pas si la DB est indisponible."""
        handler = self._make_handler(app)
        test_logger = logging.getLogger("test.dbhandler.resilience")
        test_logger.addHandler(handler)
        try:
            with app.app_context():
                db.session.remove()
                db.drop_all()

                # Ne doit PAS lever d'exception
                test_logger.error("This should not crash")

                # Recreer les tables pour les tests suivants
                db.create_all()
        finally:
            test_logger.removeHandler(handler)

    def test_skip_without_app_context(self):
        """Sans contexte Flask, le handler skip silencieusement."""
        handler = DBHandler(app=None, level=logging.WARNING)
        test_logger = logging.getLogger("test.dbhandler.nocontext")
        test_logger.addHandler(handler)
        try:
            # Simuler l'absence de contexte Flask (le conftest a un context session-scope)
            with patch("app.logging_db.has_app_context", return_value=False):
                test_logger.error("No context available")
            # Si on arrive ici sans crash, c'est OK
        finally:
            test_logger.removeHandler(handler)

    def test_no_recursion(self, app, db):
        """Le handler ne cause pas de recursion infinie."""
        handler = self._make_handler(app)
        root = logging.getLogger()
        root.addHandler(handler)
        try:
            with app.app_context():
                logging.getLogger("app.logging_db").error("Recursion test")
                logging.getLogger("sqlalchemy.engine").warning("SA test")

                logs = AppLog.query.filter(
                    AppLog.module.in_(["app.logging_db", "sqlalchemy.engine"])
                ).all()
                assert len(logs) == 0
        finally:
            root.removeHandler(handler)

    def test_extra_fields_captured(self, app, db):
        """Les champs extra du LogRecord sont stockes dans le JSON extra."""
        handler = self._make_handler(app)
        test_logger = logging.getLogger("test.dbhandler.extra")
        test_logger.addHandler(handler)
        try:
            with app.app_context():
                test_logger.error("With extras", extra={"scan_id": 42, "url": "http://test"})

                log = AppLog.query.filter_by(module="test.dbhandler.extra").first()
                assert log is not None
                assert log.extra is not None
                assert log.extra.get("scan_id") == 42
        finally:
            test_logger.removeHandler(handler)
