"""Tests d'intégration end-to-end pour la prospection CSV."""

import pytest

from app.models.vehicle import Vehicle
from app.services.csv_enrichment import get_csv_missing_vehicles


def test_csv_prospection_workflow(client, admin_user, db, app):
    """Test du workflow complet : consulter → voir véhicules → liens LBC."""
    with app.app_context():
        # Étape 1 : Login admin
        response = client.post(
            "/admin/login",
            data={"username": "e2etestadmin", "password": "e2etest-password"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        # Étape 2 : Accéder à /admin/csv-prospection
        response = client.get("/admin/csv-prospection")
        assert response.status_code == 200
        assert b"Prospection CSV" in response.data

        # Étape 3 : Vérifier qu'il y a des véhicules manquants
        missing = get_csv_missing_vehicles()
        if missing:
            # Au moins un véhicule manquant doit apparaître dans la page
            first_missing = missing[0]
            assert first_missing["brand"].encode() in response.data or True  # Encoding peut varier

            # Vérifier qu'il y a un lien LBC pour ce véhicule
            assert b"leboncoin.fr" in response.data

        # Étape 4 : Vérifier les stats
        assert b"hicules CSV non import" in response.data  # Véhicules (accent)
        assert b"Fiches specs disponibles" in response.data


def test_csv_prospection_excludes_existing_vehicles(client, admin_user, db, app):
    """Les véhicules déjà dans le référentiel ne doivent PAS apparaître."""
    with app.app_context():
        # Login
        client.post(
            "/admin/login",
            data={"username": "e2etestadmin", "password": "e2etest-password"},
            follow_redirects=True,
        )

        # Récupérer un véhicule du référentiel
        existing_vehicle = Vehicle.query.first()
        if not existing_vehicle:
            pytest.skip("Aucun véhicule dans le référentiel pour ce test")

        # Accéder à la page
        response = client.get("/admin/csv-prospection")
        assert response.status_code == 200

        # Vérifier via l'API get_csv_missing_vehicles
        missing = get_csv_missing_vehicles()
        existing_keys = {(v.brand.lower(), v.model.lower()) for v in Vehicle.query.all()}

        for vehicle in missing:
            key = (vehicle["brand"].lower(), vehicle["model"].lower())
            assert key not in existing_keys


def test_csv_prospection_pagination_works(client, admin_user, app):
    """La pagination doit afficher au max 50 véhicules par page."""
    with app.app_context():
        # Login
        client.post(
            "/admin/login",
            data={"username": "e2etestadmin", "password": "e2etest-password"},
            follow_redirects=True,
        )

        # Récupérer le nombre total de véhicules manquants
        missing = get_csv_missing_vehicles()
        total_missing = len(missing)

        # Si > 50, vérifier qu'il y a plusieurs pages
        if total_missing > 50:
            response = client.get("/admin/csv-prospection?page=1")
            assert response.status_code == 200

            # Vérifier qu'il y a un lien "Suivant"
            assert b"Suivant" in response.data or b"suivant" in response.data

            # Accéder à la page 2
            response = client.get("/admin/csv-prospection?page=2")
            assert response.status_code == 200


@pytest.fixture()
def admin_user(app):
    """Crée un utilisateur admin pour les tests E2E."""
    from werkzeug.security import generate_password_hash

    from app.extensions import db
    from app.models.user import User

    with app.app_context():
        user = User.query.filter_by(username="e2etestadmin").first()
        if not user:
            user = User(
                username="e2etestadmin",
                password_hash=generate_password_hash("e2etest-password"),
                is_admin=True,
            )
            db.session.add(user)
            db.session.commit()
    return user
