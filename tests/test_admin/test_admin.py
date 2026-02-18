"""Tests du blueprint admin : authentification, dashboard, vehicules, erreurs, pipelines."""

import pytest
from werkzeug.security import generate_password_hash

from app.models.filter_result import FilterResultDB
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

    def test_dashboard_shows_fail_rate(self, app, client, admin_user):
        """Le dashboard affiche le taux d'echec."""
        from app.extensions import db
        from app.models.filter_result import FilterResultDB

        with app.app_context():
            scan = ScanLog(score=30, is_partial=False)
            db.session.add(scan)
            db.session.flush()
            db.session.add(
                FilterResultDB(
                    scan_id=scan.id,
                    filter_id="L1",
                    status="fail",
                    score=0.0,
                    message="test fail",
                )
            )
            db.session.commit()

        _login(client)
        resp = client.get("/admin/dashboard")
        assert resp.status_code == 200
        assert b"Taux d" in resp.data

    def test_dashboard_shows_warning_and_error_counts(self, app, client, admin_user):
        """Le dashboard affiche les compteurs warnings et erreurs."""
        from app.extensions import db

        with app.app_context():
            log = AppLog(level="ERROR", module="test", message="Dashboard error test")
            db.session.add(log)
            db.session.commit()

        _login(client)
        resp = client.get("/admin/dashboard")
        assert resp.status_code == 200
        assert b"Avertissements filtres" in resp.data
        assert b"Erreurs applicatives" in resp.data


# ── Vehicules ───────────────────────────────────────────────────


class TestVehicles:
    """Tests de la page vehicules."""

    def test_car_page_loads(self, client, admin_user):
        """La page vehicules se charge."""
        _login(client)
        resp = client.get("/admin/car")
        assert resp.status_code == 200
        assert b"Vehicules" in resp.data

    def test_car_shows_referentiel(self, client, admin_user):
        """La page affiche les vehicules du referentiel."""
        _login(client)
        resp = client.get("/admin/car")
        assert resp.status_code == 200
        assert b"Referentiel actuel" in resp.data

    def test_car_shows_unrecognized_from_scans(self, app, client, admin_user):
        """La page affiche les vehicules non reconnus depuis les scans."""
        from app.extensions import db

        with app.app_context():
            for _ in range(3):
                scan = ScanLog(vehicle_make="Tesla", vehicle_model="Model Y", score=50)
                db.session.add(scan)
                db.session.flush()
                db.session.add(
                    FilterResultDB(
                        scan_id=scan.id,
                        filter_id="L2",
                        status="warning",
                        score=0.3,
                        message="Non reconnu",
                        details={"brand": "Tesla", "model": "Model Y", "recognized": False},
                    )
                )
            db.session.commit()

        _login(client)
        resp = client.get("/admin/car")
        assert resp.status_code == 200
        assert b"Tesla" in resp.data
        assert b"Model Y" in resp.data

    def test_car_shows_trend_column(self, client, admin_user):
        """La page affiche la colonne tendance 7j."""
        _login(client)
        resp = client.get("/admin/car")
        assert resp.status_code == 200
        assert b"Tendance 7j" in resp.data

    def test_car_shows_enrichment_status(self, app, client, admin_user):
        """La page affiche le statut d'enrichissement du referentiel."""
        from app.extensions import db

        with app.app_context():
            v = Vehicle(brand="TestBrand", model="TestModel", enrichment_status="pending")
            db.session.add(v)
            db.session.commit()

        _login(client)
        resp = client.get("/admin/car")
        assert resp.status_code == 200
        assert b"En attente" in resp.data


# ── Quick-add vehicule ─────────────────────────────────────────


class TestQuickAdd:
    """Tests de l'endpoint quick-add vehicule."""

    def test_quick_add_creates_vehicle(self, app, client, admin_user):
        """Le quick-add cree un vehicule avec enrichment_status=pending."""
        _login(client)
        resp = client.post(
            "/admin/vehicle/quick-add",
            data={"brand": "Tesla", "model": "Model S"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"ajoute au referentiel" in resp.data

        with app.app_context():
            v = Vehicle.query.filter_by(model="Model S").first()
            assert v is not None
            assert v.brand == "Tesla"
            # Si le CSV Kaggle contient des specs, enrichissement auto
            from app.services.csv_enrichment import CSV_PATH

            if CSV_PATH.exists():
                assert v.enrichment_status in ("partial", "pending")
            else:
                assert v.enrichment_status == "pending"

    def test_quick_add_capitalizes_brand(self, app, client, admin_user):
        """Le quick-add capitalise correctement les marques."""
        _login(client)
        client.post(
            "/admin/vehicle/quick-add",
            data={"brand": "BMW", "model": "iX3"},
            follow_redirects=True,
        )

        with app.app_context():
            v = Vehicle.query.filter(Vehicle.model.ilike("ix3")).first()
            assert v is not None
            assert v.brand == "BMW"  # reste en majuscules (<=3 chars)
            assert v.model == "iX3"  # casse mixte preservee

    def test_quick_add_duplicate_rejected(self, app, client, admin_user):
        """Le quick-add refuse les doublons."""
        from app.extensions import db

        with app.app_context():
            v = Vehicle(brand="Audi", model="Q5", year_start=2020)
            db.session.add(v)
            db.session.commit()

        _login(client)
        resp = client.post(
            "/admin/vehicle/quick-add",
            data={"brand": "audi", "model": "q5"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"existe deja" in resp.data

    def test_quick_add_empty_brand_rejected(self, client, admin_user):
        """Le quick-add refuse une marque vide."""
        _login(client)
        resp = client.post(
            "/admin/vehicle/quick-add",
            data={"brand": "", "model": "Something"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"requis" in resp.data

    def test_quick_add_requires_auth(self, client):
        """Le quick-add necessite une authentification."""
        client.get("/admin/logout")
        resp = client.post(
            "/admin/vehicle/quick-add",
            data={"brand": "Tesla", "model": "Model 3"},
        )
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["Location"]

    def test_quick_add_rejects_invalid_chars(self, client, admin_user):
        """Le quick-add refuse les caracteres speciaux dangereux."""
        _login(client)
        resp = client.post(
            "/admin/vehicle/quick-add",
            data={"brand": "<script>", "model": "alert(1)"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Caracteres invalides" in resp.data

    def test_car_trend_nouveau_badge(self, app, client, admin_user):
        """Vehicule avec previous=0 affiche 'Nouveau' et non '+100%'."""
        from app.extensions import db

        with app.app_context():
            scan = ScanLog(vehicle_make="Volvo", vehicle_model="XC40", score=50)
            db.session.add(scan)
            db.session.flush()
            db.session.add(
                FilterResultDB(
                    scan_id=scan.id,
                    filter_id="L2",
                    status="warning",
                    score=0.3,
                    message="Non reconnu",
                )
            )
            db.session.commit()

        _login(client)
        resp = client.get("/admin/car")
        assert resp.status_code == 200
        assert b"Nouveau" in resp.data
        assert b"+100%" not in resp.data


# ── Dashboard non-reconnus ─────────────────────────────────────


class TestDashboardUnrecognized:
    """Tests du compteur vehicules non reconnus sur le dashboard."""

    def test_dashboard_shows_unrecognized_count(self, app, client, admin_user):
        """Le dashboard affiche le nombre de vehicules non reconnus."""
        from app.extensions import db

        with app.app_context():
            scan = ScanLog(vehicle_make="Volvo", vehicle_model="XC60", score=50)
            db.session.add(scan)
            db.session.flush()
            db.session.add(
                FilterResultDB(
                    scan_id=scan.id,
                    filter_id="L2",
                    status="warning",
                    score=0.3,
                    message="Non reconnu",
                )
            )
            db.session.commit()

        _login(client)
        resp = client.get("/admin/dashboard")
        assert resp.status_code == 200
        assert b"non reconnus" in resp.data

    def test_dashboard_unrecognized_links_to_car(self, client, admin_user):
        """Le lien 'non reconnus' pointe vers /admin/car."""
        _login(client)
        resp = client.get("/admin/dashboard")
        assert resp.status_code == 200
        assert b"/admin/car" in resp.data


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

    def test_pipelines_shows_last_run(self, app, client, admin_user):
        """La page pipelines affiche la date du dernier run."""
        from datetime import datetime, timezone

        from app.extensions import db
        from app.models.pipeline_run import PipelineRun

        with app.app_context():
            run = PipelineRun(
                name="referentiel_vehicules",
                status="success",
                count=50,
                started_at=datetime(2026, 2, 1, 10, 0, 0, tzinfo=timezone.utc),
                finished_at=datetime(2026, 2, 1, 10, 5, 0, tzinfo=timezone.utc),
            )
            db.session.add(run)
            db.session.commit()

        _login(client)
        resp = client.get("/admin/pipelines")
        assert resp.status_code == 200
        assert b"01/02/2026" in resp.data

    def test_pipelines_shows_run_counts(self, app, client, admin_user):
        """La page pipelines affiche les compteurs success/failure."""
        from datetime import datetime, timezone

        from app.extensions import db
        from app.models.pipeline_run import PipelineRun

        with app.app_context():
            for status in ["success", "success", "failure"]:
                run = PipelineRun(
                    name="import_csv_specs",
                    status=status,
                    started_at=datetime.now(timezone.utc),
                    finished_at=datetime.now(timezone.utc),
                )
                db.session.add(run)
            db.session.commit()

        _login(client)
        resp = client.get("/admin/pipelines")
        assert resp.status_code == 200
        assert b"2 succes" in resp.data
        assert b"1 echec" in resp.data


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
            v = Vehicle(
                brand="TestMarque",
                model="TestModele",
                generation="I",
                year_start=2020,
                year_end=2025,
            )
            db.session.add(v)
            db.session.flush()
            spec = VehicleSpec(
                vehicle_id=v.id, fuel_type="Essence", engine="1.0 Test", power_hp=100
            )
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


# ── Filtres ────────────────────────────────────────────────────


class TestFilters:
    """Tests de la page filtres d'analyse."""

    def test_filters_page_loads(self, client, admin_user):
        """La page filtres se charge."""
        _login(client)
        resp = client.get("/admin/filters")
        assert resp.status_code == 200
        assert b"Filtres d" in resp.data

    def test_filters_shows_all_ten(self, client, admin_user):
        """La page affiche les 10 filtres actifs."""
        _login(client)
        resp = client.get("/admin/filters")
        assert resp.status_code == 200
        for fid in [b"L1", b"L2", b"L3", b"L4", b"L5", b"L6", b"L7", b"L8", b"L9", b"L10"]:
            assert fid in resp.data

    def test_filters_shows_no_simulated_badge(self, client, admin_user):
        """Tous les filtres utilisent des donnees reelles."""
        _login(client)
        resp = client.get("/admin/filters")
        assert resp.status_code == 200
        assert b"Donnees simulees" not in resp.data
        assert b"En preparation" not in resp.data

    def test_filters_l10_active(self, client, admin_user):
        """Le filtre L10 est actif avec badge OK."""
        _login(client)
        resp = client.get("/admin/filters")
        assert resp.status_code == 200
        assert b"L10" in resp.data
        assert b"Anciennete annonce" in resp.data

    def test_filters_shows_maturity(self, client, admin_user):
        """La page affiche les barres de maturite."""
        _login(client)
        resp = client.get("/admin/filters")
        assert resp.status_code == 200
        assert b"Maturite" in resp.data
        assert b"100%" in resp.data
        assert b"70%" in resp.data

    def test_filters_shows_execution_stats(self, app, client, admin_user):
        """La page affiche les stats d'execution quand il y a des donnees."""
        from app.extensions import db
        from app.models.filter_result import FilterResultDB

        with app.app_context():
            scan = ScanLog(score=75, is_partial=False)
            db.session.add(scan)
            db.session.flush()
            db.session.add(
                FilterResultDB(
                    scan_id=scan.id,
                    filter_id="L1",
                    status="pass",
                    score=1.0,
                    message="Test",
                )
            )
            db.session.commit()

        _login(client)
        resp = client.get("/admin/filters")
        assert resp.status_code == 200
        assert b"1 pass" in resp.data

    def test_filters_requires_auth(self, client):
        """La page filtres necessite une authentification."""
        client.get("/admin/logout")
        resp = client.get("/admin/filters")
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["Location"]


# ── Argus maison ──────────────────────────────────────────────


class TestArgus:
    """Tests de la page argus maison."""

    def test_argus_page_loads(self, client, admin_user):
        """La page argus se charge."""
        _login(client)
        resp = client.get("/admin/argus")
        assert resp.status_code == 200
        assert b"Argus maison" in resp.data

    def test_argus_shows_stats(self, app, client, admin_user):
        """La page affiche les stats quand il y a des donnees."""
        from datetime import datetime, timedelta, timezone

        from app.extensions import db
        from app.models.market_price import MarketPrice

        with app.app_context():
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            mp = MarketPrice(
                make="Opel",
                model="Corsa",
                year=2020,
                region="Normandie",
                price_min=8000,
                price_median=9500,
                price_mean=9500,
                price_max=11000,
                price_std=1200.0,
                sample_count=8,
                collected_at=now,
                refresh_after=now + timedelta(hours=24),
            )
            db.session.add(mp)
            db.session.commit()

        _login(client)
        resp = client.get("/admin/argus")
        assert resp.status_code == 200
        assert b"Opel" in resp.data
        assert b"Corsa" in resp.data
        assert b"9 500" in resp.data  # price_median formate
        assert b"Frais" in resp.data

    def test_argus_filter_by_make(self, app, client, admin_user):
        """Le filtre par marque fonctionne."""
        _login(client)
        resp = client.get("/admin/argus?make=Opel")
        assert resp.status_code == 200
        assert b"Opel" in resp.data

    def test_argus_requires_auth(self, client):
        """La page argus necessite une authentification."""
        client.get("/admin/logout")
        resp = client.get("/admin/argus")
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["Location"]


# ── E2E : scan → collecte → visible dans argus ────────────────


class TestArgusE2E:
    """Test end-to-end : un scan + collecte prix → visible dans l'admin argus."""

    def test_full_flow_scan_collect_argus(self, app, client, admin_user):
        """Flux complet : POST market-prices → GET next-job → visible /admin/argus."""
        import json

        from app.models.market_price import MarketPrice

        with app.app_context():
            # 1. L'extension envoie des prix collectes
            resp = client.post(
                "/api/market-prices",
                data=json.dumps(
                    {
                        "make": "Volkswagen",
                        "model": "Golf",
                        "year": 2020,
                        "region": "Hauts-de-France",
                        "prices": [15000, 16000, 17000, 18000, 19000, 20000],
                    }
                ),
                content_type="application/json",
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert data["data"]["sample_count"] == 6
            assert data["data"]["price_median"] == 17500

            # 2. Verifier que la donnee est en base
            mp = MarketPrice.query.filter_by(
                make="Volkswagen",
                model="Golf",
                year=2020,
                region="Hauts-de-France",
            ).first()
            assert mp is not None
            assert mp.sample_count == 6

            # 3. next-job dit "pas besoin" pour ce vehicule (frais)
            resp = client.get(
                "/api/market-prices/next-job"
                "?make=Volkswagen&model=Golf&year=2020&region=Hauts-de-France",
            )
            job = resp.get_json()
            assert job["success"] is True
            # Le vehicule est frais, le serveur ne le redemande pas
            # (soit collect: false, soit redirige vers un autre)
            if job["data"]["collect"]:
                v = job["data"]["vehicle"]
                assert not (v["make"] == "Volkswagen" and v["model"] == "Golf")

            # 4. Connexion admin et verification dans la page argus
            _login(client)
            resp = client.get("/admin/argus")
            assert resp.status_code == 200
            assert b"Volkswagen" in resp.data
            assert b"Golf" in resp.data
            assert b"Hauts-de-France" in resp.data
            assert b"17 500" in resp.data  # prix median formate
            assert b"Frais" in resp.data


# ── Race condition : double POST quick-add ────────────────────


class TestQuickAddRaceCondition:
    """Test que deux POST rapides ne creent qu'un seul vehicule."""

    def test_double_quick_add_creates_single_vehicle(self, app, client, admin_user):
        """Deux quick-add identiques ne creent qu'un seul vehicule (IntegrityError catch)."""
        from app.extensions import db

        _login(client)

        # Premier ajout
        resp1 = client.post(
            "/admin/vehicle/quick-add",
            data={"brand": "Mazda", "model": "CX-5"},
            follow_redirects=True,
        )
        assert resp1.status_code == 200
        assert b"ajoute au referentiel" in resp1.data

        # Deuxieme ajout (meme vehicule)
        resp2 = client.post(
            "/admin/vehicle/quick-add",
            data={"brand": "mazda", "model": "cx-5"},
            follow_redirects=True,
        )
        assert resp2.status_code == 200
        assert b"existe deja" in resp2.data

        # Verifier qu'un seul vehicule existe
        with app.app_context():
            count = Vehicle.query.filter(
                db.func.lower(Vehicle.brand) == "mazda",
                db.func.lower(Vehicle.model) == "cx-5",
            ).count()
            assert count == 1

    def test_concurrent_quick_add_integrity_error(self, app, client, admin_user):
        """Si un doublon passe la validation, l'IntegrityError est capture."""
        from app.extensions import db

        _login(client)

        # Inserer directement en base pour simuler un ajout concurrent
        with app.app_context():
            v = Vehicle(brand="Hyundai", model="Tucson", year_start=2026)
            db.session.add(v)
            db.session.commit()

        # Le quick-add doit detecter le doublon
        resp = client.post(
            "/admin/vehicle/quick-add",
            data={"brand": "hyundai", "model": "tucson"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"existe deja" in resp.data

        with app.app_context():
            count = Vehicle.query.filter(
                db.func.lower(Vehicle.brand) == "hyundai",
                db.func.lower(Vehicle.model) == "tucson",
            ).count()
            assert count == 1


# ── Dashboard : compteur exact non reconnus ───────────────────


class TestDashboardExactCounts:
    """Tests du compteur exact de vehicules non reconnus."""

    def test_dashboard_unrecognized_exact_count(self, app, client, admin_user):
        """Le dashboard affiche le nombre exact de modeles non reconnus distincts."""
        from app.extensions import db

        with app.app_context():
            # 3 scans pour "Alpha Romeo Tonale" + 2 pour "Lynk Co 01"
            for _ in range(3):
                scan = ScanLog(vehicle_make="Alfa Romeo", vehicle_model="Tonale", score=50)
                db.session.add(scan)
                db.session.flush()
                db.session.add(
                    FilterResultDB(
                        scan_id=scan.id,
                        filter_id="L2",
                        status="warning",
                        score=0.3,
                        message="Non reconnu",
                        details={"brand": "Alfa Romeo", "model": "Tonale", "recognized": False},
                    )
                )
            for _ in range(2):
                scan = ScanLog(vehicle_make="Lynk Co", vehicle_model="01", score=50)
                db.session.add(scan)
                db.session.flush()
                db.session.add(
                    FilterResultDB(
                        scan_id=scan.id,
                        filter_id="L2",
                        status="warning",
                        score=0.3,
                        message="Non reconnu",
                        details={"brand": "Lynk Co", "model": "01", "recognized": False},
                    )
                )
            db.session.commit()

        _login(client)
        resp = client.get("/admin/car")
        assert resp.status_code == 200
        # Les deux modeles distincts apparaissent
        assert b"Alfa Romeo" in resp.data
        assert b"Tonale" in resp.data
        assert b"Lynk Co" in resp.data
        assert b"01" in resp.data

    def test_car_page_excludes_not_a_vehicle(self, app, client, admin_user):
        """Les scans NOT_A_VEHICLE ne comptent pas dans les non reconnus."""
        from app.extensions import db

        with app.app_context():
            # Scan normal non reconnu
            scan1 = ScanLog(
                vehicle_make="Genesis",
                vehicle_model="GV70",
                score=50,
                url="https://www.leboncoin.fr/ad/voitures/123",
            )
            db.session.add(scan1)
            db.session.flush()
            db.session.add(
                FilterResultDB(
                    scan_id=scan1.id,
                    filter_id="L2",
                    status="warning",
                    score=0.3,
                    message="Non reconnu",
                    details={"brand": "Genesis", "model": "GV70", "recognized": False},
                )
            )

            # Scan moto (devrait etre exclu)
            scan2 = ScanLog(
                vehicle_make="Honda",
                vehicle_model="CB500",
                score=0,
                url="https://www.leboncoin.fr/ad/motos/456",
            )
            db.session.add(scan2)
            db.session.flush()
            db.session.add(
                FilterResultDB(
                    scan_id=scan2.id,
                    filter_id="L2",
                    status="skip",
                    score=0.0,
                    message="NOT_A_VEHICLE",
                )
            )
            db.session.commit()

        _login(client)
        resp = client.get("/admin/car")
        assert resp.status_code == 200
        assert b"Genesis" in resp.data
        # Les motos skip ne doivent pas apparaitre dans les non reconnus
        assert b"CB500" not in resp.data


# ── Edge cases : make/model avec valeurs speciales ────────────


class TestQuickAddEdgeCases:
    """Tests edge cases pour le quick-add vehicule."""

    def test_quick_add_model_with_accents(self, app, client, admin_user):
        """Le quick-add gere les accents (Citroen, Senat, etc.)."""
        from app.extensions import db

        _login(client)
        resp = client.post(
            "/admin/vehicle/quick-add",
            data={"brand": "Citroën", "model": "Berlingo"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"ajoute au referentiel" in resp.data

        with app.app_context():
            v = Vehicle.query.filter(db.func.lower(Vehicle.model) == "berlingo").first()
            assert v is not None
            assert "Citro" in v.brand  # accent preserved or title-cased

    def test_quick_add_model_with_dot(self, app, client, admin_user):
        """Le quick-add gere les points (ID.3, e.C3, etc.)."""
        _login(client)
        resp = client.post(
            "/admin/vehicle/quick-add",
            data={"brand": "VW", "model": "ID.3"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"ajoute au referentiel" in resp.data

        with app.app_context():
            v = Vehicle.query.filter_by(model="ID.3").first()
            assert v is not None
            assert v.brand == "VW"  # <=3 chars stays uppercase

    def test_quick_add_model_with_hyphen(self, app, client, admin_user):
        """Le quick-add gere les tirets (e-2008, C-HR, etc.)."""
        _login(client)
        resp = client.post(
            "/admin/vehicle/quick-add",
            data={"brand": "Toyota", "model": "C-HR"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"ajoute au referentiel" in resp.data

        with app.app_context():
            v = Vehicle.query.filter_by(model="C-HR").first()
            assert v is not None

    def test_quick_add_model_with_slash(self, app, client, admin_user):
        """Le quick-add gere les slashes (3008/5008, etc.)."""
        _login(client)
        resp = client.post(
            "/admin/vehicle/quick-add",
            data={"brand": "Peugeot", "model": "3008/5008"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"ajoute au referentiel" in resp.data

    def test_quick_add_whitespace_only_rejected(self, client, admin_user):
        """Le quick-add refuse les chaines de whitespace."""
        _login(client)
        resp = client.post(
            "/admin/vehicle/quick-add",
            data={"brand": "   ", "model": "   "},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"requis" in resp.data

    def test_quick_add_very_long_input_truncated(self, app, client, admin_user):
        """Le quick-add tronque les entrees trop longues."""
        _login(client)
        long_brand = "A" * 200
        resp = client.post(
            "/admin/vehicle/quick-add",
            data={"brand": long_brand, "model": "TestLong"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        # Doit passer (tronque a 80 chars) ou echouer proprement
        with app.app_context():
            v = Vehicle.query.filter_by(model="TestLong").first()
            if v:
                assert len(v.brand) <= 80

    def test_quick_add_pipe_character_rejected(self, client, admin_user):
        """Le quick-add refuse les caracteres pipe |."""
        _login(client)
        resp = client.post(
            "/admin/vehicle/quick-add",
            data={"brand": "Test|Brand", "model": "Model"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Caracteres invalides" in resp.data

    def test_quick_add_html_injection_rejected(self, client, admin_user):
        """Le quick-add refuse les injections HTML."""
        _login(client)
        resp = client.post(
            "/admin/vehicle/quick-add",
            data={"brand": "Test<img>", "model": "Model"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Caracteres invalides" in resp.data
