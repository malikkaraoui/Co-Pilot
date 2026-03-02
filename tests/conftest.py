"""Shared pytest fixtures for Co-Pilot tests."""

from unittest.mock import patch

import pytest

from app import create_app
from app.extensions import db as _db


@pytest.fixture(scope="session")
def app():
    """Create application for testing."""
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
        yield app
        _db.drop_all()


@pytest.fixture()
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture(autouse=True)
def _mock_l7_siret_api():
    """Empeche tout appel reseau vers les APIs entreprise dans les tests.

    Retourne systematiquement une entreprise active fictive (France).
    Les tests unitaires de L7 qui mockent deja _call_fr_api ne sont pas affectes
    car leur patch local prend precedence.
    """
    fake_response = {
        "etat_administratif": "A",
        "nom_complet": "Entreprise Test SARL",
    }
    with patch(
        "app.filters.l7_siret.L7SiretFilter._call_fr_api",
        return_value=fake_response,
    ):
        yield


@pytest.fixture()
def db(app):
    """Database session for a test -- rolls back after each test."""
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.rollback()
