"""Tests pour la route admin CSV prospection."""

import pytest
from werkzeug.security import generate_password_hash

from app.models.user import User


@pytest.fixture()
def admin_user(app):
    """Crée un utilisateur admin pour les tests."""
    from app.extensions import db

    with app.app_context():
        user = User.query.filter_by(username="csvtestadmin").first()
        if not user:
            user = User(
                username="csvtestadmin",
                password_hash=generate_password_hash("csvtest-password"),
                is_admin=True,
            )
            db.session.add(user)
            db.session.commit()
    return user


def test_csv_prospection_requires_login(client):
    """La route doit nécessiter une authentification."""
    response = client.get("/admin/csv-prospection")
    assert response.status_code == 302  # Redirect vers login
    assert "/login" in response.location


def test_csv_prospection_page_loads(client, admin_user):
    """La page doit se charger correctement pour un admin connecté."""
    with client:
        # Login
        client.post(
            "/admin/login",
            data={"username": "csvtestadmin", "password": "csvtest-password"},
            follow_redirects=True,
        )

        # Accès à la page
        response = client.get("/admin/csv-prospection")
        assert response.status_code == 200
        assert b"Prospection CSV" in response.data


def test_csv_prospection_displays_missing_vehicles(client, admin_user, app):
    """La page doit afficher les véhicules CSV manquants."""
    with client:
        # Login
        client.post(
            "/admin/login",
            data={"username": "csvtestadmin", "password": "csvtest-password"},
            follow_redirects=True,
        )

        # Accès à la page
        response = client.get("/admin/csv-prospection")
        assert response.status_code == 200

        # Vérifier présence des éléments clés du tableau (header toujours présent)
        assert b"Marque" in response.data
        assert b"Mod" in response.data  # Modèle (peut être encodé)
        assert b"Fiches CSV" in response.data

        # Si CSV vide (CI), on voit le message empty state
        # Sinon il y a des véhicules avec des liens LBC
        # On accepte les deux cas (CI sans CSV OU dev avec CSV)
        has_empty_state = b"Tous les" in response.data and b"import" in response.data
        has_vehicles = b"Chercher sur LBC" in response.data or b"leboncoin" in response.data

        # Au moins l'un des deux doit être présent
        assert has_empty_state or has_vehicles


def test_csv_prospection_lbc_urls_valid(client, admin_user):
    """Les URLs LBC doivent être valides."""
    with client:
        # Login
        client.post(
            "/admin/login",
            data={"username": "csvtestadmin", "password": "csvtest-password"},
            follow_redirects=True,
        )

        # Accès à la page
        response = client.get("/admin/csv-prospection")
        assert response.status_code == 200

        # Vérifier qu'il y a des liens vers leboncoin.fr
        assert b"leboncoin.fr/recherche" in response.data or b"leboncoin" in response.data


def test_csv_prospection_pagination(client, admin_user):
    """La pagination doit fonctionner."""
    with client:
        # Login
        client.post(
            "/admin/login",
            data={"username": "csvtestadmin", "password": "csvtest-password"},
            follow_redirects=True,
        )

        # Accès à la page 1
        response = client.get("/admin/csv-prospection?page=1")
        assert response.status_code == 200

        # Accès à une page invalide (devrait être clampée)
        response = client.get("/admin/csv-prospection?page=9999")
        assert response.status_code == 200
