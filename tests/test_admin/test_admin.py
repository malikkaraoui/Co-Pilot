"""Tests du blueprint admin : authentification, dashboard, vehicules, erreurs, pipelines."""

import pytest
from werkzeug.security import generate_password_hash

from app.models.log import AppLog
from app.models.scan import ScanLog
from app.models.user import User


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
