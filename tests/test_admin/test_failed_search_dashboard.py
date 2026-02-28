"""Tests pour le dashboard admin des recherches echouees."""

import json

import pytest
from werkzeug.security import generate_password_hash

from app.extensions import db as _db
from app.models.failed_search import FailedSearch
from app.models.user import User


@pytest.fixture()
def admin_client(app, db):
    """Client HTTP authentifie en tant qu'admin."""
    user = User.query.filter_by(username="testadmin_fs").first()
    if not user:
        user = User(
            username="testadmin_fs",
            password_hash=generate_password_hash("testpass"),
            is_admin=True,
        )
        _db.session.add(user)
        _db.session.commit()

    client = app.test_client()
    client.post(
        "/admin/login",
        data={"username": "testadmin_fs", "password": "testpass"},
        follow_redirects=True,
    )
    return client


class TestFailedSearchDashboard:
    """Tests des routes admin failed-searches."""

    def test_dashboard_loads_empty(self, admin_client):
        resp = admin_client.get("/admin/failed-searches")
        assert resp.status_code == 200
        assert b"Monitoring Recherches" in resp.data

    def test_dashboard_shows_kpis(self, admin_client, db):
        for _ in range(3):
            db.session.add(
                FailedSearch(
                    make="BMW",
                    model="320",
                    year=2021,
                    region="Zurich",
                    country="CH",
                    severity="high",
                )
            )
        db.session.add(
            FailedSearch(
                make="AUDI",
                model="A3",
                year=2020,
                region="Geneve",
                country="CH",
                status="resolved",
                resolved=True,
                severity="low",
            )
        )
        db.session.commit()

        resp = admin_client.get("/admin/failed-searches")
        assert resp.status_code == 200
        assert b"Nouvelles" in resp.data
        assert b"En cours" in resp.data
        assert b"Taux resolution" in resp.data

    def test_filter_by_status(self, admin_client, db):
        db.session.add(
            FailedSearch(
                make="VW",
                model="Golf",
                year=2022,
                region="Berne",
                status="new",
            )
        )
        db.session.add(
            FailedSearch(
                make="VW",
                model="Golf",
                year=2022,
                region="Zurich",
                status="investigating",
            )
        )
        db.session.commit()

        resp = admin_client.get("/admin/failed-searches?status=new")
        assert resp.status_code == 200

    def test_filter_by_country(self, admin_client, db):
        db.session.add(
            FailedSearch(
                make="RENAULT",
                model="Clio",
                year=2022,
                region="Bretagne",
                country="FR",
            )
        )
        db.session.add(
            FailedSearch(
                make="VW",
                model="Golf",
                year=2022,
                region="Zurich",
                country="CH",
            )
        )
        db.session.commit()

        resp = admin_client.get("/admin/failed-searches?country=CH")
        assert resp.status_code == 200

    def test_detail_page_loads(self, admin_client, db):
        db.session.add(
            FailedSearch(
                make="BMW",
                model="X3",
                year=2023,
                region="Geneve",
                country="CH",
                search_log=json.dumps([{"step": 1, "precision": 5, "ads_found": 0}]),
            )
        )
        db.session.commit()

        resp = admin_client.get("/admin/failed-searches/BMW/X3")
        assert resp.status_code == 200
        assert b"BMW" in resp.data
        assert b"X3" in resp.data

    def test_detail_page_404_for_unknown(self, admin_client):
        resp = admin_client.get("/admin/failed-searches/UNKNOWN/MODEL")
        assert resp.status_code == 404

    def test_update_status_to_investigating(self, admin_client, db):
        fs = FailedSearch(
            make="AUDI",
            model="Q5",
            year=2023,
            region="Vaud",
            status="new",
        )
        db.session.add(fs)
        db.session.commit()

        resp = admin_client.post(
            f"/admin/failed-searches/{fs.id}/status",
            data={"status": "investigating", "note": "En cours d'analyse"},
            follow_redirects=True,
        )
        assert resp.status_code == 200

        db.session.refresh(fs)
        assert fs.status == "investigating"

    def test_update_status_to_resolved(self, admin_client, db):
        fs = FailedSearch(
            make="PEUGEOT",
            model="308",
            year=2022,
            region="Zurich",
            status="investigating",
        )
        db.session.add(fs)
        db.session.commit()

        resp = admin_client.post(
            f"/admin/failed-searches/{fs.id}/status",
            data={"status": "resolved", "note": "Token corrige"},
            follow_redirects=True,
        )
        assert resp.status_code == 200

        db.session.refresh(fs)
        assert fs.status == "resolved"
        assert fs.resolved is True

    def test_add_note(self, admin_client, db):
        fs = FailedSearch(
            make="VW",
            model="Tiguan",
            year=2021,
            region="Berne",
            status="new",
        )
        db.session.add(fs)
        db.session.commit()

        resp = admin_client.post(
            f"/admin/failed-searches/{fs.id}/note",
            data={"note": "Verifier le token DOM"},
            follow_redirects=True,
        )
        assert resp.status_code == 200

        db.session.refresh(fs)
        notes = fs.get_notes()
        assert len(notes) == 1
        assert notes[0]["message"] == "Verifier le token DOM"

    def test_invalid_status_rejected(self, admin_client, db):
        fs = FailedSearch(
            make="BMW",
            model="320",
            year=2021,
            region="Geneve",
        )
        db.session.add(fs)
        db.session.commit()

        resp = admin_client.post(
            f"/admin/failed-searches/{fs.id}/status",
            data={"status": "invalid_status"},
            follow_redirects=True,
        )
        assert resp.status_code == 200

        db.session.refresh(fs)
        assert fs.status == "new"  # Unchanged

    def test_legacy_resolve_endpoint(self, admin_client, db):
        fs = FailedSearch(
            make="SEAT",
            model="Leon",
            year=2020,
            region="Geneve",
        )
        db.session.add(fs)
        db.session.commit()

        resp = admin_client.post(
            f"/admin/failed-searches/{fs.id}/resolve",
            data={"note": "test legacy"},
            follow_redirects=True,
        )
        assert resp.status_code == 200

        db.session.refresh(fs)
        assert fs.status == "resolved"
        assert fs.resolved is True
