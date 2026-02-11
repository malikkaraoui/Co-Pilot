"""Shared pytest fixtures for Co-Pilot tests."""

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


@pytest.fixture()
def db(app):
    """Database session for a test -- rolls back after each test."""
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.rollback()
