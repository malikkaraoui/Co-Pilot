"""Tests du blueprint admin : authentification, dashboard, vehicules, erreurs, pipelines."""

import pytest
from werkzeug.security import generate_password_hash

from app.models.log import AppLog
from app.models.scan import ScanLog
from app.models.user import User
from app.models.vehicle import Vehicle, VehicleSpec


@pytest.fixture()
def admin_user(app):
    """Cree un utilisateur admin pour les tests."""
    from app.extensions import db

    with app.app_context():
        user = User.query.filter_by(username="testadmin").first()
        if not user:
            user = User(
                username="testadmin",
                password_hash=generate_password_hash("testpass"),
                is_admin=True,
            )
            db.session.add(user)
            db.session.commit()
    return user


def _login(client, username="testadmin", password="testpass"):
    """Helper pour se connecter."""
    return client.post(
        "/admin/login",
        data={"username": username, "password": password},
        follow_redirects=True,
    )


# ── Authentification ────────────────────────────────────────────


class TestLogin:
    """Tests de la page de connexion admin."""

    def test_login_page_renders(self, client):
        """La page de login s'affiche."""
        resp = client.get("/admin/login")
        assert resp.status_code == 200
        assert b"Co-Pilot Admin" in resp.data

    def test_redirect_to_login_when_unauthenticated(self, client):
        """Un visiteur non connecte est redirige vers login."""
        resp = client.get("/admin/dashboard")
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["Location"]

    def test_login_success(self, client, admin_user):
        """Connexion reussie redirige vers le dashboard."""
        resp = _login(client)
        assert resp.status_code == 200
        assert b"Dashboard" in resp.data

    def test_login_failure(self, client, admin_user):
        """Identifiants invalides affichent un message d'erreur."""
        client.get("/admin/logout")  # ensure clean session
        resp = _login(client, password="mauvais")
        assert b"Identifiants invalides" in resp.data

    def test_logout(self, client, admin_user):
        """La deconnexion redirige vers login."""
        _login(client)
        resp = client.get("/admin/logout", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Connectez-vous" in resp.data


# ── Dashboard ───────────────────────────────────────────────────


class TestDashboard:
    """Tests de la page dashboard."""

    def test_dashboard_loads(self, client, admin_user):
        """Le dashboard se charge apres connexion."""
        _login(client)
        resp = client.get("/admin/dashboard")
        assert resp.status_code == 200
        assert b"Scans totaux" in resp.data

    def test_dashboard_with_scans(self, app, client, admin_user):
        """Le dashboard affiche les stats quand il y a des scans."""
        from app.extensions import db

        with app.app_context():
            scan = ScanLog(score=75, is_partial=False)
            db.session.add(scan)
            db.session.commit()

        _login(client)
        resp = client.get("/admin/dashboard")
        assert resp.status_code == 200
        assert b"75" in resp.data


# ── Vehicules ───────────────────────────────────────────────────


class TestVehicles:
    """Tests de la page vehicules."""

    def test_vehicles_page_loads(self, client, admin_user):
        """La page vehicules se charge."""
        _login(client)
        resp = client.get("/admin/vehicles")
        assert resp.status_code == 200
        assert b"Vehicules" in resp.data

    def test_vehicles_shows_referentiel(self, client, admin_user):
        """La page affiche les vehicules du referentiel."""
        _login(client)
        resp = client.get("/admin/vehicles")
        assert resp.status_code == 200
        assert b"Referentiel actuel" in resp.data


# ── Logs erreurs ────────────────────────────────────────────────


class TestErrors:
    """Tests de la page logs erreurs."""

    def test_errors_page_loads(self, client, admin_user):
        """La page erreurs se charge."""
        _login(client)
        resp = client.get("/admin/errors")
        assert resp.status_code == 200
        assert b"Logs" in resp.data

    def test_errors_with_logs(self, app, client, admin_user):
        """La page affiche les logs existants."""
        from app.extensions import db

        with app.app_context():
            log = AppLog(level="ERROR", module="test", message="Test error log")
            db.session.add(log)
            db.session.commit()

        _login(client)
        resp = client.get("/admin/errors?level=ERROR")
        assert resp.status_code == 200
        assert b"Test error log" in resp.data

    def test_errors_filter_warning(self, app, client, admin_user):
        """Le filtre WARNING fonctionne."""
        from app.extensions import db

        with app.app_context():
            log = AppLog(level="WARNING", module="test", message="Attention test")
            db.session.add(log)
            db.session.commit()

        _login(client)
        resp = client.get("/admin/errors?level=WARNING")
        assert resp.status_code == 200
        assert b"Attention test" in resp.data


# ── Pipelines ───────────────────────────────────────────────────


class TestPipelines:
    """Tests de la page pipelines."""

    def test_pipelines_page_loads(self, client, admin_user):
        """La page pipelines se charge."""
        _login(client)
        resp = client.get("/admin/pipelines")
        assert resp.status_code == 200
        assert b"Pipelines" in resp.data

    def test_pipelines_shows_status(self, client, admin_user):
        """La page affiche le statut des pipelines."""
        _login(client)
        resp = client.get("/admin/pipelines")
        assert resp.status_code == 200
        assert b"Referentiel vehicules" in resp.data
        assert b"Argus geolocalise" in resp.data


# ── Base Vehicules ─────────────────────────────────────────────


class TestDatabase:
    """Tests de la page Base Vehicules."""

    def test_database_page_loads(self, client, admin_user):
        """La page base vehicules se charge."""
        _login(client)
        resp = client.get("/admin/database")
        assert resp.status_code == 200
        assert b"Base Vehicules" in resp.data

    def test_database_shows_stats(self, app, client, admin_user):
        """La page affiche les stats marques/modeles/specs."""
        from app.extensions import db

        with app.app_context():
            v = Vehicle(brand="TestMarque", model="TestModele", generation="I",
                        year_start=2020, year_end=2025)
            db.session.add(v)
            db.session.flush()
            spec = VehicleSpec(vehicle_id=v.id, fuel_type="Essence",
                               engine="1.0 Test", power_hp=100)
            db.session.add(spec)
            db.session.commit()

        _login(client)
        resp = client.get("/admin/database")
        assert resp.status_code == 200
        assert b"TestMarque" in resp.data
        assert b"TestModele" in resp.data

    def test_database_filter_by_brand(self, app, client, admin_user):
        """Le filtre par marque fonctionne."""
        from app.extensions import db

        with app.app_context():
            v1 = Vehicle(brand="FilterA", model="M1", year_start=2020)
            v2 = Vehicle(brand="FilterB", model="M2", year_start=2020)
            db.session.add_all([v1, v2])
            db.session.flush()
            db.session.add(VehicleSpec(vehicle_id=v1.id, engine="1.0", fuel_type="Essence"))
            db.session.add(VehicleSpec(vehicle_id=v2.id, engine="2.0", fuel_type="Diesel"))
            db.session.commit()

        _login(client)
        resp = client.get("/admin/database?brand=FilterA")
        assert resp.status_code == 200
        assert b"FilterA" in resp.data
        # FilterB appears in chart JS but NOT in table rows
        assert b"<strong>FilterB</strong>" not in resp.data
        assert b"1 resultats" in resp.data

    def test_database_filter_by_fuel(self, app, client, admin_user):
        """Le filtre par carburant fonctionne."""
        from app.extensions import db

        with app.app_context():
            v = Vehicle(brand="FuelTest", model="X", year_start=2020)
            db.session.add(v)
            db.session.flush()
            db.session.add(VehicleSpec(vehicle_id=v.id, engine="EV", fuel_type="Electrique"))
            db.session.commit()

        _login(client)
        resp = client.get("/admin/database?fuel=Electrique")
        assert resp.status_code == 200
        assert b"FuelTest" in resp.data
