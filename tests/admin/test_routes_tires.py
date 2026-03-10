"""Tests pour la route admin pneus (/admin/tires)."""

import json

import pytest
from werkzeug.security import generate_password_hash

from app.models.user import User


@pytest.fixture()
def admin_user(app):
    """Crée un utilisateur admin pour les tests."""
    from app.extensions import db

    with app.app_context():
        user = User.query.filter_by(username="tiretestadmin").first()
        if not user:
            user = User(
                username="tiretestadmin",
                password_hash=generate_password_hash("tiretest-password"),
                is_admin=True,
            )
            db.session.add(user)
            db.session.commit()
    return user


@pytest.fixture()
def sample_tire_data(app):
    """Injecte un minimum de données Vehicle/TireSize pour rendre la page non vide."""
    from app.extensions import db
    from app.models.tire_size import TireSize
    from app.models.vehicle import Vehicle

    with app.app_context():
        v = Vehicle.query.filter_by(brand="Renault", model="Clio").first()
        if not v:
            v = Vehicle(brand="Renault", model="Clio")
            db.session.add(v)

        t = TireSize.query.filter_by(make="volkswagen", model="golf", generation="golf-vii").first()
        if not t:
            t = TireSize(
                make="volkswagen",
                model="golf",
                generation="golf-vii",
                year_start=2012,
                year_end=2021,
                dimensions=json.dumps(
                    [
                        {
                            "size": "205/55R16",
                            "load_index": 91,
                            "speed_index": "V",
                            "is_stock": True,
                        },
                        {
                            "size": "225/45R17",
                            "load_index": 91,
                            "speed_index": "W",
                            "is_stock": True,
                        },
                    ]
                ),
                source="allopneus",
                source_url="https://www.allopneus.com/vehicule/volkswagen/golf/golf-vii",
                dimension_count=2,
                request_count=3,
            )
            db.session.add(t)

        db.session.commit()


def _login(client):
    return client.post(
        "/admin/login",
        data={"username": "tiretestadmin", "password": "tiretest-password"},
        follow_redirects=True,
    )


def test_tires_requires_login(client):
    """La route doit nécessiter une authentification."""
    response = client.get("/admin/tires")
    assert response.status_code == 302
    assert "/login" in response.location


def test_tires_page_loads(client, admin_user, sample_tire_data):
    """La page doit se charger correctement pour un admin connecté."""
    with client:
        _login(client)

        response = client.get("/admin/tires")
        assert response.status_code == 200
        assert b"Pneus" in response.data
        assert b"Couverture" in response.data

        client.get("/admin/logout")
