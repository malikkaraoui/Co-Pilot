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
        prices_20 = list(range(12000, 22000, 500))  # 20 prix
        resp = client.post(
            "/api/market-prices",
            data=json.dumps(
                {
                    "make": "Peugeot",
                    "model": "208",
                    "year": 2021,
                    "region": "Ile-de-France",
                    "prices": prices_20,
                    "precision": 4,
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["sample_count"] == 20

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
        """POST avec moins de 20 prix retourne 400."""
        resp = client.post(
            "/api/market-prices",
            data=json.dumps(
                {
                    "make": "Peugeot",
                    "model": "208",
                    "year": 2021,
                    "region": "Ile-de-France",
                    "prices": [12000, 13000, 14000, 15000, 16000],  # < 20
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_submit_filters_low_prices(self, app, client):
        """Les prix < 500 EUR sont filtres. Si pas assez de prix valides, retourne 400."""
        # 20 prix dont tous < 500 → 0 valides apres filtrage
        resp = client.post(
            "/api/market-prices",
            data=json.dumps(
                {
                    "make": "Peugeot",
                    "model": "208",
                    "year": 2021,
                    "region": "Ile-de-France",
                    "prices": list(range(100, 600, 25)),  # 20 prix, tous < 500 sauf le dernier
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "prix valides" in resp.get_json()["message"].lower()

    def test_submit_with_fuel(self, app, client):
        """POST avec fuel stocke la motorisation."""
        resp = client.post(
            "/api/market-prices",
            data=json.dumps(
                {
                    "make": "Seat",
                    "model": "Ibiza",
                    "year": 2024,
                    "region": "PACA",
                    "prices": list(range(14000, 24000, 500)),  # 20 prix
                    "fuel": "essence",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

        with app.app_context():
            mp = MarketPrice.query.filter_by(
                make="Seat",
                model="Ibiza",
                year=2024,
                fuel="essence",
            ).first()
            assert mp is not None
            assert mp.fuel == "essence"

    def test_submit_with_price_details(self, app, client):
        """POST avec price_details stocke les details par prix."""
        prices_20 = list(range(12000, 22000, 500))
        price_details = [
            {"price": p, "year": 2021, "km": 40000 + i * 1000, "fuel": "Diesel"}
            for i, p in enumerate(prices_20)
        ]
        resp = client.post(
            "/api/market-prices",
            data=json.dumps(
                {
                    "make": "Renault",
                    "model": "Captur",
                    "year": 2021,
                    "region": "Bretagne",
                    "prices": prices_20,
                    "price_details": price_details,
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 200

        with app.app_context():
            mp = MarketPrice.query.filter_by(make="Renault", model="Captur", year=2021).first()
            assert mp is not None
            details = mp.get_calculation_details()
            assert details is not None
            assert details["kept_details"] is not None
            assert len(details["kept_details"]) > 0
            first = details["kept_details"][0]
            assert "year" in first
            assert "km" in first
            assert "fuel" in first

    def test_submit_with_hp_range_and_lbc_estimate(self, app, client):
        """POST with hp_range, fiscal_hp, lbc estimates stores them."""
        prices_20 = list(range(12000, 22000, 500))
        resp = client.post(
            "/api/market-prices",
            data=json.dumps(
                {
                    "make": "Renault",
                    "model": "Talisman",
                    "year": 2016,
                    "region": "Ile-de-France",
                    "prices": prices_20,
                    "fuel": "diesel",
                    "hp_range": "120-150",
                    "fiscal_hp": 7,
                    "lbc_estimate_low": 12000,
                    "lbc_estimate_high": 15000,
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 200
        with app.app_context():
            mp = MarketPrice.query.filter_by(make="Renault", model="Talisman", year=2016).first()
            assert mp is not None
            assert mp.hp_range == "120-150"
            assert mp.fiscal_hp == 7
            assert mp.lbc_estimate_low == 12000
            assert mp.lbc_estimate_high == 15000

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
                    "prices": list(range(12000, 22000, 500)),  # 20 prix
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

    def test_redirects_to_partial_vehicle_first(self, app, client):
        """Vehicles with enrichment_status=partial should be prioritized for redirect."""
        with app.app_context():
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            region = "Corse"

            # Current vehicle: fresh data
            mp = MarketPrice(
                make="Lotus",
                model="Elise",
                year=2022,
                region=region,
                price_min=30000,
                price_median=35000,
                price_mean=35000,
                price_max=40000,
                price_std=3000.0,
                sample_count=5,
                collected_at=now,
                refresh_after=now + timedelta(hours=24),
            )
            db.session.add(mp)

            # Create fresh MarketPrice for ALL existing vehicles in this region
            # so only our two test vehicles are candidates
            all_vehicles = Vehicle.query.all()
            for v in all_vehicles:
                if not v.year_start:
                    continue
                mid_y = (v.year_start + (v.year_end or v.year_start)) // 2
                existing = MarketPrice.query.filter_by(
                    make=v.brand, model=v.model, region=region
                ).first()
                if not existing:
                    db.session.add(
                        MarketPrice(
                            make=v.brand,
                            model=v.model,
                            year=mid_y,
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
                    )

            # Complete vehicle: never collected in Corse (delete its fresh MP)
            v_complete = Vehicle.query.filter_by(brand="Koenigsegg", model="Agera").first()
            if not v_complete:
                v_complete = Vehicle(
                    brand="Koenigsegg",
                    model="Agera",
                    year_start=2019,
                    year_end=2024,
                    enrichment_status="complete",
                )
                db.session.add(v_complete)

            # Partial vehicle: never collected, should be prioritized
            v_partial = Vehicle.query.filter_by(brand="Pagani", model="Huayra").first()
            if not v_partial:
                v_partial = Vehicle(
                    brand="Pagani",
                    model="Huayra",
                    year_start=2018,
                    year_end=2024,
                    enrichment_status="partial",
                )
                db.session.add(v_partial)
            db.session.commit()

            # Remove any accidental fresh MP for our test vehicles
            MarketPrice.query.filter_by(make="Koenigsegg", model="Agera", region=region).delete()
            MarketPrice.query.filter_by(make="Pagani", model="Huayra", region=region).delete()
            db.session.commit()

            resp = client.get(
                f"/api/market-prices/next-job?make=Lotus&model=Elise&year=2022&region={region}"
            )
            data = resp.get_json()
            assert data["success"] is True
            assert data["data"]["collect"] is True
            assert data["data"].get("redirect") is True
            # Partial vehicle should be chosen over complete
            assert data["data"]["vehicle"]["make"] == "Pagani"
            assert data["data"]["vehicle"]["model"] == "Huayra"


class TestSearchLogTransparency:
    """Tests de la transparence cascade (search_log)."""

    def test_submit_with_search_log(self, app, client):
        """POST avec search_log stocke les etapes dans calculation_details."""
        prices_20 = list(range(12000, 22000, 500))
        search_log = [
            {
                "step": 1,
                "precision": 4,
                "location_type": "region",
                "year_spread": 1,
                "filters_applied": ["fuel", "gearbox", "hp", "km"],
                "ads_found": 8,
                "url": "https://www.leboncoin.fr/recherche?category=2&test=1",
                "was_selected": False,
                "reason": "8 annonces < 20 minimum",
            },
            {
                "step": 2,
                "precision": 3,
                "location_type": "national",
                "year_spread": 1,
                "filters_applied": ["fuel", "gearbox", "hp", "km"],
                "ads_found": 25,
                "url": "https://www.leboncoin.fr/recherche?category=2&test=2",
                "was_selected": True,
                "reason": "25 annonces >= 20 minimum",
            },
        ]
        resp = client.post(
            "/api/market-prices",
            data=json.dumps(
                {
                    "make": "Citroen",
                    "model": "C3",
                    "year": 2021,
                    "region": "Lorraine",
                    "prices": prices_20,
                    "precision": 3,
                    "search_log": search_log,
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 200

        with app.app_context():
            mp = MarketPrice.query.filter_by(make="Citroen", model="C3", year=2021).first()
            assert mp is not None
            details = mp.get_calculation_details()
            assert details is not None
            assert "search_steps" in details
            assert len(details["search_steps"]) == 2
            selected = [s for s in details["search_steps"] if s["was_selected"]]
            assert len(selected) == 1
            assert selected[0]["ads_found"] == 25
            assert selected[0]["url"].startswith("https://")

    def test_submit_without_search_log_backward_compat(self, app, client):
        """POST sans search_log (ancienne extension) fonctionne toujours."""
        prices_20 = list(range(12000, 22000, 500))
        resp = client.post(
            "/api/market-prices",
            data=json.dumps(
                {
                    "make": "Citroen",
                    "model": "C4",
                    "year": 2022,
                    "region": "Normandie",
                    "prices": prices_20,
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 200

        with app.app_context():
            mp = MarketPrice.query.filter_by(make="Citroen", model="C4", year=2022).first()
            details = mp.get_calculation_details()
            # search_steps est None (pas envoye) -- pas d'erreur
            assert details.get("search_steps") is None


class TestBonusJobs:
    """Tests for bonus_jobs in GET /api/market-prices/next-job."""

    def _make_fresh_mp(self, make, model, year, region, fuel=None):
        """Helper: create a fresh MarketPrice entry."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        return MarketPrice(
            make=make,
            model=model,
            year=year,
            region=region,
            fuel=fuel,
            price_min=10000,
            price_median=14000,
            price_mean=14000,
            price_max=18000,
            price_std=1414.0,
            sample_count=20,
            collected_at=now,
            refresh_after=now + timedelta(hours=24),
        )

    def _make_stale_mp(self, make, model, year, region, fuel=None, days_old=10):
        """Helper: create a stale MarketPrice entry (>7 days)."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        old = now - timedelta(days=days_old)
        return MarketPrice(
            make=make,
            model=model,
            year=year,
            region=region,
            fuel=fuel,
            price_min=10000,
            price_median=14000,
            price_mean=14000,
            price_max=18000,
            price_std=1414.0,
            sample_count=20,
            collected_at=old,
            refresh_after=old + timedelta(hours=24),
        )

    def test_bonus_jobs_returns_missing_regions(self, app, client):
        """When current vehicle has fresh data, bonus_jobs lists missing regions."""
        with app.app_context():
            db.session.add(self._make_fresh_mp("Peugeot", "3008", 2021, "Bretagne", "diesel"))
            db.session.commit()
            resp = client.get(
                "/api/market-prices/next-job"
                "?make=Peugeot&model=3008&year=2021&region=Bretagne&fuel=diesel"
            )
            data = resp.get_json()
            assert data["success"] is True
            bonus = data["data"].get("bonus_jobs", [])
            assert len(bonus) <= 2
            for job in bonus:
                assert job["region"] != "Bretagne"
                assert job["make"] == "Peugeot"
                assert job["model"] == "3008"

    def test_bonus_jobs_refresh_stale(self, app, client):
        """When all 13 regions covered, bonus_jobs returns the 2 oldest for refresh."""
        with app.app_context():
            regions = [
                "Île-de-France",
                "Auvergne-Rhône-Alpes",
                "Provence-Alpes-Côte d'Azur",
                "Occitanie",
                "Nouvelle-Aquitaine",
                "Hauts-de-France",
                "Grand Est",
                "Bretagne",
                "Pays de la Loire",
                "Normandie",
                "Bourgogne-Franche-Comté",
                "Centre-Val de Loire",
                "Corse",
            ]
            for i, r in enumerate(regions):
                if r in ("Bretagne", "Occitanie"):
                    db.session.add(
                        self._make_stale_mp(
                            "Renault", "Captur", 2022, r, "essence", days_old=15 - i
                        )
                    )
                else:
                    db.session.add(self._make_fresh_mp("Renault", "Captur", 2022, r, "essence"))
            db.session.commit()
            resp = client.get(
                "/api/market-prices/next-job"
                "?make=Renault&model=Captur&year=2022&region=Bretagne&fuel=essence"
            )
            data = resp.get_json()
            bonus = data["data"].get("bonus_jobs", [])
            assert len(bonus) >= 1
            bonus_regions = {j["region"] for j in bonus}
            assert bonus_regions <= {"Bretagne", "Occitanie"}

    def test_bonus_jobs_empty_when_all_fresh(self, app, client):
        """When all 13 regions have fresh data, bonus_jobs is empty."""
        with app.app_context():
            regions = [
                "Île-de-France",
                "Auvergne-Rhône-Alpes",
                "Provence-Alpes-Côte d'Azur",
                "Occitanie",
                "Nouvelle-Aquitaine",
                "Hauts-de-France",
                "Grand Est",
                "Bretagne",
                "Pays de la Loire",
                "Normandie",
                "Bourgogne-Franche-Comté",
                "Centre-Val de Loire",
                "Corse",
            ]
            for r in regions:
                db.session.add(self._make_fresh_mp("Toyota", "Yaris", 2023, r, "essence"))
            db.session.commit()
            resp = client.get(
                "/api/market-prices/next-job"
                "?make=Toyota&model=Yaris&year=2023&region=Bretagne&fuel=essence"
            )
            data = resp.get_json()
            bonus = data["data"].get("bonus_jobs", [])
            assert bonus == []

    def test_bonus_jobs_without_fuel(self, app, client):
        """Without fuel param, bonus_jobs still works."""
        with app.app_context():
            db.session.add(self._make_fresh_mp("Dacia", "Sandero", 2022, "Grand Est"))
            db.session.commit()
            resp = client.get(
                "/api/market-prices/next-job?make=Dacia&model=Sandero&year=2022&region=Grand+Est"
            )
            data = resp.get_json()
            bonus = data["data"].get("bonus_jobs", [])
            assert len(bonus) == 2
            for job in bonus:
                assert job["region"] != "Grand Est"
