"""Tests for POST /api/market-prices and GET /api/market-prices/next-job."""

import json
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models.market_price import MarketPrice
from app.models.vehicle import Vehicle


class TestMarketPricesAPI:
    """Tests de la route POST /api/market-prices."""

    def test_submit_valid_prices(self, app, client):
        """POST avec des donnees valides retourne 200."""
        resp = client.post(
            "/api/market-prices",
            data=json.dumps(
                {
                    "make": "Peugeot",
                    "model": "208",
                    "year": 2021,
                    "region": "Ile-de-France",
                    "prices": [12000, 13000, 14000, 15000, 16000],
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["sample_count"] == 5
        assert data["data"]["price_median"] == 14000

    def test_submit_no_json_returns_400(self, client):
        """POST sans JSON retourne 400."""
        resp = client.post(
            "/api/market-prices",
            data="not json",
            content_type="text/plain",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False
        assert data["error"] == "VALIDATION_ERROR"

    def test_submit_missing_fields_returns_400(self, client):
        """POST avec champs manquants retourne 400."""
        resp = client.post(
            "/api/market-prices",
            data=json.dumps({"make": "Peugeot"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_submit_too_few_prices_returns_400(self, client):
        """POST avec moins de 3 prix retourne 400."""
        resp = client.post(
            "/api/market-prices",
            data=json.dumps(
                {
                    "make": "Peugeot",
                    "model": "208",
                    "year": 2021,
                    "region": "Ile-de-France",
                    "prices": [12000, 13000],  # < 3
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_submit_filters_low_prices(self, app, client):
        """Les prix < 500 EUR sont filtres. Si pas assez de prix valides, retourne 400."""
        resp = client.post(
            "/api/market-prices",
            data=json.dumps(
                {
                    "make": "Peugeot",
                    "model": "208",
                    "year": 2021,
                    "region": "Ile-de-France",
                    "prices": [100, 200, 300],  # tous < 500
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "prix valides" in resp.get_json()["message"].lower()

    def test_submit_invalid_year_returns_400(self, client):
        """POST avec annee hors limites retourne 400."""
        resp = client.post(
            "/api/market-prices",
            data=json.dumps(
                {
                    "make": "Peugeot",
                    "model": "208",
                    "year": 1800,
                    "region": "Ile-de-France",
                    "prices": [12000, 13000, 14000],
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 400


class TestNextMarketJob:
    """Tests de la route GET /api/market-prices/next-job."""

    def test_returns_current_vehicle_if_stale(self, app, client):
        """Sans MarketPrice existant, retourne le vehicule courant."""
        with app.app_context():
            resp = client.get(
                "/api/market-prices/next-job?make=Fiat&model=Punto&year=2018&region=Grand+Est",
            )
            data = resp.get_json()
            assert data["success"] is True
            assert data["data"]["collect"] is True
            assert data["data"]["vehicle"]["make"] == "Fiat"
            assert data["data"]["vehicle"]["model"] == "Punto"
            assert data["data"]["region"] == "Grand Est"

    def test_returns_other_vehicle_if_current_fresh(self, app, client):
        """Vehicule courant a jour → retourne un autre du referentiel."""
        with app.app_context():
            # Creer un MarketPrice frais pour Dacia Sandero
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            mp = MarketPrice(
                make="Dacia",
                model="Sandero",
                year=2022,
                region="Occitanie",
                price_min=12000,
                price_median=14000,
                price_mean=14000,
                price_max=16000,
                price_std=1414.0,
                sample_count=5,
                collected_at=now,
                refresh_after=now + timedelta(hours=24),
            )
            db.session.add(mp)

            # Ajouter un vehicule dans le referentiel (pas de MarketPrice)
            v = Vehicle.query.filter_by(brand="Renault", model="Clio V").first()
            if not v:
                v = Vehicle(brand="Renault", model="Clio V", year_start=2019, year_end=2025)
                db.session.add(v)
            db.session.commit()

            resp = client.get(
                "/api/market-prices/next-job?make=Dacia&model=Sandero&year=2022&region=Occitanie",
            )
            data = resp.get_json()
            assert data["success"] is True
            assert data["data"]["collect"] is True
            # Doit rediriger vers un autre vehicule (pas Dacia Sandero)
            v = data["data"]["vehicle"]
            assert not (v["make"] == "Dacia" and v["model"] == "Sandero")

    def test_returns_no_collect_if_all_fresh(self, app, client):
        """Tout est a jour → collect: false."""
        with app.app_context():
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            region = "Centre-Val de Loire"

            # MarketPrice frais pour le vehicule courant
            mp = MarketPrice(
                make="Toyota",
                model="Yaris",
                year=2023,
                region=region,
                price_min=12000,
                price_median=14000,
                price_mean=14000,
                price_max=16000,
                price_std=1414.0,
                sample_count=5,
                collected_at=now,
                refresh_after=now + timedelta(hours=24),
            )
            db.session.add(mp)

            # Creer un MarketPrice frais pour chaque vehicule du referentiel
            # dans cette region (pour que le serveur ne trouve aucun candidat)
            all_vehicles = Vehicle.query.all()
            for v in all_vehicles:
                if not v.year_start:
                    continue
                mid_year = (v.year_start + (v.year_end or v.year_start)) // 2
                existing = MarketPrice.query.filter_by(
                    make=v.brand,
                    model=v.model,
                    region=region,
                ).first()
                if not existing:
                    fresh = MarketPrice(
                        make=v.brand,
                        model=v.model,
                        year=mid_year,
                        region=region,
                        price_min=10000,
                        price_median=12000,
                        price_mean=12000,
                        price_max=14000,
                        price_std=1000.0,
                        sample_count=5,
                        collected_at=now,
                        refresh_after=now + timedelta(hours=24),
                    )
                    db.session.add(fresh)
            db.session.commit()

            resp = client.get(
                f"/api/market-prices/next-job?make=Toyota&model=Yaris&year=2023&region={region}",
            )
            data = resp.get_json()
            assert data["success"] is True
            assert data["data"]["collect"] is False

    def test_missing_params_returns_no_collect(self, client):
        """Parametres manquants → collect: false."""
        resp = client.get("/api/market-prices/next-job?make=Peugeot")
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["collect"] is False
