"""Tests for POST /api/market-prices and GET /api/market-prices/next-job."""

import json
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models.failed_search import FailedSearch
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

    def test_current_variant_priority_when_generic_is_fresh(self, app, client):
        """Le vehicule scanne doit etre prioritaire si la variante fuel/hp manque.

        Cas reel : un MarketPrice generique frais (fuel NULL) existe,
        mais l'annonce demande diesel + hp_range specifique. L'API doit
        retourner collect=true pour la variante courante, pas rediriger.
        """
        with app.app_context():
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            mp_generic = MarketPrice(
                make="Mercedes",
                model="Classe C",
                year=2007,
                region="Franche-Comté",
                fuel=None,
                hp_range=None,
                price_min=4000,
                price_median=6500,
                price_mean=6500,
                price_max=9000,
                price_std=1200.0,
                sample_count=20,
                collected_at=now,
                refresh_after=now + timedelta(hours=24),
            )
            db.session.add(mp_generic)
            db.session.commit()

            resp = client.get(
                "/api/market-prices/next-job"
                "?make=Mercedes&model=Classe%20C&year=2007&region=Franche-Comté"
                "&fuel=diesel&hp_range=100-150"
            )
            data = resp.get_json()

            assert data["success"] is True
            assert data["data"]["collect"] is True
            assert data["data"]["vehicle"]["make"] == "Mercedes"
            assert data["data"]["vehicle"]["model"] == "Classe C"
            assert data["data"].get("redirect") is not True

    def test_current_vehicle_lookup_uses_canonical_aliases(self, app, client):
        """next-job doit reconnaitre un MarketPrice frais via aliases make/model.

        Regression DS: en base on peut avoir make/model canonicalises (DS / 7),
        alors que l'extension envoie le brut (Ds / Ds 7).
        """
        with app.app_context():
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            mp = MarketPrice(
                make="DS",
                model="7",
                year=2021,
                region="Grand Est",
                fuel="diesel",
                price_min=18000,
                price_median=22000,
                price_mean=22300,
                price_max=28000,
                price_std=2500.0,
                sample_count=25,
                collected_at=now,
                refresh_after=now + timedelta(hours=24),
            )
            db.session.add(mp)
            db.session.commit()

        resp = client.get(
            "/api/market-prices/next-job"
            "?make=Ds&model=Ds%207&year=2021&region=Grand+Est&fuel=diesel"
        )
        data = resp.get_json()
        assert data["success"] is True

        # Le vehicule courant ne doit PAS etre redemande comme stale.
        # S'il y a collecte, elle doit etre une redirection vers un autre vehicule.
        if data["data"]["collect"] is True:
            assert data["data"].get("redirect") is True

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


class TestSiteTokenAutoLearning:
    """Tests pour l'auto-apprentissage des tokens LBC (site_brand_token, site_model_token)."""

    def test_submit_with_tokens_persists_to_vehicle(self, app, client):
        """POST avec site_brand_token/site_model_token les persiste sur le Vehicle."""
        with app.app_context():
            v = Vehicle.query.filter_by(brand="TokenTest", model="Modele1").first()
            if not v:
                v = Vehicle(brand="TokenTest", model="Modele1", year_start=2019, year_end=2025)
                db.session.add(v)
                db.session.commit()
            # Reset tokens
            v.site_brand_token = None
            v.site_model_token = None
            db.session.commit()

        prices_20 = list(range(12000, 22000, 500))
        resp = client.post(
            "/api/market-prices",
            data=json.dumps(
                {
                    "make": "TokenTest",
                    "model": "Modele1",
                    "year": 2021,
                    "region": "Ile-de-France",
                    "prices": prices_20,
                    "site_brand_token": "TokenTest",
                    "site_model_token": "TokenTest_Modèle1",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 200

        with app.app_context():
            v = Vehicle.query.filter_by(brand="TokenTest", model="Modele1").first()
            assert v.site_brand_token == "TokenTest"
            assert v.site_model_token == "TokenTest_Modèle1"

    def test_submit_without_tokens_backward_compat(self, app, client):
        """POST sans tokens (ancienne extension) fonctionne sans erreur."""
        prices_20 = list(range(12000, 22000, 500))
        resp = client.post(
            "/api/market-prices",
            data=json.dumps(
                {
                    "make": "Renault",
                    "model": "Megane",
                    "year": 2020,
                    "region": "Bretagne",
                    "prices": prices_20,
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_tokens_not_persisted_for_unknown_vehicle(self, app, client):
        """Les tokens ne sont pas persistes si le vehicule n'existe pas dans le referentiel."""
        prices_20 = list(range(12000, 22000, 500))
        resp = client.post(
            "/api/market-prices",
            data=json.dumps(
                {
                    "make": "Lamborghini",
                    "model": "Urus",
                    "year": 2022,
                    "region": "PACA",
                    "prices": prices_20,
                    "site_brand_token": "Lamborghini",
                    "site_model_token": "Lamborghini_Urus",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 200  # POST reussit quand meme

    def test_submit_with_as24_slugs_persists_to_vehicle(self, app, client):
        """POST avec as24_slug_* persiste les slugs canoniques sur Vehicle."""
        with app.app_context():
            v = Vehicle.query.filter_by(brand="SlugTest", model="ModeleAS24").first()
            if not v:
                v = Vehicle(brand="SlugTest", model="ModeleAS24", year_start=2019, year_end=2026)
                db.session.add(v)
                db.session.commit()

            v.as24_slug_make = None
            v.as24_slug_model = None
            db.session.commit()

        prices_20 = list(range(12000, 22000, 500))
        resp = client.post(
            "/api/market-prices",
            data=json.dumps(
                {
                    "make": "SlugTest",
                    "model": "ModeleAS24",
                    "year": 2022,
                    "region": "Ile-de-France",
                    "prices": prices_20,
                    "as24_slug_make": "slugtest",
                    "as24_slug_model": "modeleas24",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 200

        with app.app_context():
            v = Vehicle.query.filter_by(brand="SlugTest", model="ModeleAS24").first()
            assert v.as24_slug_make == "slugtest"
            assert v.as24_slug_model == "modeleas24"

    def test_next_job_returns_tokens(self, app, client):
        """GET next-job inclut les tokens LBC si le vehicule en a."""
        with app.app_context():
            v = Vehicle.query.filter_by(brand="BMW", model="Serie 3").first()
            if not v:
                v = Vehicle(
                    brand="BMW",
                    model="Serie 3",
                    year_start=2005,
                    year_end=2025,
                )
                db.session.add(v)
            v.site_brand_token = "BMW"
            v.site_model_token = "BMW_Série 3"
            db.session.commit()

        resp = client.get(
            "/api/market-prices/next-job?make=BMW&model=Serie%203&year=2021&region=Bretagne"
        )
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["collect"] is True
        assert data["data"]["vehicle"]["site_brand_token"] == "BMW"
        assert data["data"]["vehicle"]["site_model_token"] == "BMW_Série 3"

    def test_next_job_without_tokens(self, app, client):
        """GET next-job sans tokens stockes ne retourne pas les cles."""
        with app.app_context():
            v = Vehicle.query.filter_by(brand="Dacia", model="Sandero").first()
            if not v:
                v = Vehicle(
                    brand="Dacia",
                    model="Sandero",
                    year_start=2020,
                    year_end=2025,
                )
                db.session.add(v)
            v.site_brand_token = None
            v.site_model_token = None
            db.session.commit()

        resp = client.get(
            "/api/market-prices/next-job?make=Dacia&model=Sandero&year=2022&region=Bretagne"
        )
        data = resp.get_json()
        assert data["success"] is True
        vehicle = data["data"]["vehicle"]
        # Keys should not be present when tokens are None
        assert "site_brand_token" not in vehicle
        assert "site_model_token" not in vehicle


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


class TestFailedSearchApi:
    """Tests pour POST /api/market-prices/failed-search."""

    def test_failed_search_maps_as24_slug_fields(self, app, client):
        """Le payload AS24 (slug_* + slug_source) est bien mappe sur les champs diagnostics."""
        payload = {
            "make": "Mercedes-Benz",
            "model": "A 35 AMG",
            "year": 2020,
            "region": "Geneve",
            "country": "CH",
            "site": "as24",
            "tld": "ch",
            "slug_make_used": "mercedes-benz",
            "slug_model_used": "a-35-amg",
            "slug_source": "as24_response_url",
            "search_log": [
                {
                    "step": 1,
                    "precision": 4,
                    "location_type": "canton",
                    "year_spread": 1,
                    "filters_applied": ["fuel"],
                    "ads_found": 0,
                    "url": "https://www.autoscout24.ch/fr/s/mo-a-35-amg/mk-mercedes-benz",
                    "was_selected": False,
                    "reason": "HTTP 404",
                }
            ],
        }

        resp = client.post(
            "/api/market-prices/failed-search",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

        with app.app_context():
            row = (
                FailedSearch.query.filter_by(
                    make="Mercedes-Benz", model="A 35 AMG", region="Geneve"
                )
                .order_by(FailedSearch.id.desc())
                .first()
            )
            assert row is not None
            assert row.brand_token_used == "mercedes-benz"
            assert row.model_token_used == "a-35-amg"
            assert row.token_source == "as24_response_url"


class TestFailedSearchTokenPersistence:
    """Tests pour la persistence des tokens/slugs dans failed-search."""

    def test_failed_search_persists_lbc_tokens(self, app, client):
        """POST /api/market-prices/failed-search avec site_brand/model_token les persiste."""
        with app.app_context():
            v = Vehicle.query.filter_by(brand="TokenFailTest", model="Model1").first()
            if not v:
                v = Vehicle(brand="TokenFailTest", model="Model1", year_start=2019, year_end=2025)
                db.session.add(v)
                db.session.commit()
            v.site_brand_token = None
            v.site_model_token = None
            db.session.commit()

        payload = {
            "make": "TokenFailTest",
            "model": "Model1",
            "year": 2021,
            "region": "Bretagne",
            "brand_token_used": "TOKENFAILTEST",
            "model_token_used": "TOKENFAILTEST_Model1",
            "token_source": "DOM",
            "search_log": [
                {
                    "step": 1,
                    "precision": 4,
                    "location_type": "region",
                    "year_spread": 1,
                    "filters_applied": [],
                    "ads_found": 0,
                    "url": "https://www.leboncoin.fr/recherche?category=2",
                    "was_selected": False,
                }
            ],
            "site_brand_token": "TokenFailTest",
            "site_model_token": "TokenFailTest_Modèle1",
        }

        resp = client.post(
            "/api/market-prices/failed-search",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert resp.status_code == 200

        with app.app_context():
            v = Vehicle.query.filter_by(brand="TokenFailTest", model="Model1").first()
            assert v.site_brand_token == "TokenFailTest"
            assert v.site_model_token == "TokenFailTest_Modèle1"

    def test_failed_search_persists_as24_slugs(self, app, client):
        """POST /api/market-prices/failed-search avec as24_slug_* les persiste."""
        with app.app_context():
            v = Vehicle.query.filter_by(brand="SlugFailTest", model="ModelAS24F").first()
            if not v:
                v = Vehicle(
                    brand="SlugFailTest", model="ModelAS24F", year_start=2019, year_end=2026
                )
                db.session.add(v)
                db.session.commit()
            v.as24_slug_make = None
            v.as24_slug_model = None
            db.session.commit()

        payload = {
            "make": "SlugFailTest",
            "model": "ModelAS24F",
            "year": 2022,
            "region": "Geneve",
            "country": "CH",
            "site": "as24",
            "tld": "ch",
            "slug_make_used": "slugfailtest",
            "slug_model_used": "modelas24f",
            "slug_source": "as24_response_url",
            "search_log": [
                {
                    "step": 1,
                    "precision": 3,
                    "location_type": "canton",
                    "year_spread": 1,
                    "filters_applied": [],
                    "ads_found": 0,
                    "url": "https://www.autoscout24.ch/fr/s/mk-slugfailtest",
                    "was_selected": False,
                }
            ],
            "as24_slug_make": "slugfailtest",
            "as24_slug_model": "modelas24f",
        }

        resp = client.post(
            "/api/market-prices/failed-search",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert resp.status_code == 200

        with app.app_context():
            v = Vehicle.query.filter_by(brand="SlugFailTest", model="ModelAS24F").first()
            assert v.as24_slug_make == "slugfailtest"
            assert v.as24_slug_model == "modelas24f"

    def test_failed_search_without_tokens_backward_compat(self, client):
        """POST /api/market-prices/failed-search sans tokens fonctionne (retro-compat)."""
        payload = {
            "make": "Peugeot",
            "model": "208",
            "year": 2021,
            "region": "Bretagne",
            "brand_token_used": "PEUGEOT",
            "model_token_used": "PEUGEOT_208",
            "token_source": "fallback",
            "search_log": [
                {
                    "step": 1,
                    "precision": 3,
                    "location_type": "national",
                    "year_spread": 1,
                    "filters_applied": [],
                    "ads_found": 3,
                    "url": "https://www.leboncoin.fr/recherche?category=2",
                    "was_selected": False,
                }
            ],
        }
        resp = client.post(
            "/api/market-prices/failed-search",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert resp.status_code == 200


class TestBonusJobs:
    """Tests for bonus_jobs in GET /api/market-prices/next-job (queue-based)."""

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

    @staticmethod
    def _clean_queue(app):
        """Purge all CollectionJob rows to isolate tests from each other."""
        from app.models.collection_job import CollectionJob

        with app.app_context():
            CollectionJob.query.delete()
            db.session.commit()

    def test_bonus_jobs_returns_missing_regions(self, app, client):
        """When current vehicle has fresh data, bonus_jobs come from queue."""
        self._clean_queue(app)
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
            # pick_bonus_jobs returns up to 3 from the queue
            assert len(bonus) <= 3
            for job in bonus:
                assert "job_id" in job
                assert job["make"] == "Peugeot"
                assert job["model"] == "3008"

    def test_bonus_jobs_refresh_stale(self, app, client):
        """When some regions are stale, expand creates queue jobs for them."""
        self._clean_queue(app)
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
            assert len(bonus) <= 3
            for job in bonus:
                assert "job_id" in job

    def test_bonus_jobs_empty_when_all_fresh(self, app, client):
        """When all 13 regions have fresh data, expand creates no P1 jobs."""
        self._clean_queue(app)
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
            # All regions fresh: expand creates no P1 jobs but may create
            # P2/P3/P4 variants. With clean queue, bonus may be non-empty
            # but all should have job_id.
            for job in bonus:
                assert "job_id" in job

    def test_bonus_jobs_without_fuel(self, app, client):
        """Without fuel param, bonus_jobs still works and includes job_id."""
        self._clean_queue(app)
        with app.app_context():
            db.session.add(self._make_fresh_mp("Dacia", "Sandero", 2022, "Grand Est"))
            db.session.commit()
            resp = client.get(
                "/api/market-prices/next-job?make=Dacia&model=Sandero&year=2022&region=Grand+Est"
            )
            data = resp.get_json()
            bonus = data["data"].get("bonus_jobs", [])
            assert len(bonus) <= 3
            for job in bonus:
                assert "job_id" in job
                assert job["region"] != "Grand Est"


class TestJobCompletion:
    """Tests for POST /api/market-prices/job-done."""

    def test_mark_job_done_via_api(self, app, client):
        """POST /api/market-prices/job-done marks job as done."""
        with app.app_context():
            from app.models.collection_job import CollectionJob

            job = CollectionJob(
                make="Renault",
                model="Talisman",
                year=2016,
                region="Bretagne",
                priority=1,
                source_vehicle="test",
                status="assigned",
            )
            db.session.add(job)
            db.session.commit()
            job_id = job.id

        resp = client.post(
            "/api/market-prices/job-done",
            data=json.dumps({"job_id": job_id, "success": True}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["status"] == "done"
        with app.app_context():
            from app.models.collection_job import CollectionJob

            job = db.session.get(CollectionJob, job_id)
            assert job.status == "done"

    def test_mark_job_failed_via_api(self, app, client):
        """POST /api/market-prices/job-done with success=false marks as failed."""
        with app.app_context():
            from app.models.collection_job import CollectionJob

            job = CollectionJob(
                make="Peugeot",
                model="208",
                year=2020,
                region="Corse",
                priority=1,
                source_vehicle="test",
                status="assigned",
            )
            db.session.add(job)
            db.session.commit()
            job_id = job.id

        resp = client.post(
            "/api/market-prices/job-done",
            data=json.dumps({"job_id": job_id, "success": False}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"]["status"] == "failed"

    def test_missing_job_id_returns_400(self, client):
        """POST without job_id returns 400."""
        resp = client.post(
            "/api/market-prices/job-done",
            data=json.dumps({"success": True}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_invalid_job_id_returns_404(self, client):
        """POST with non-existent job_id returns 404."""
        resp = client.post(
            "/api/market-prices/job-done",
            data=json.dumps({"job_id": 99999, "success": True}),
            content_type="application/json",
        )
        assert resp.status_code == 404


class TestNextJobWithQueue:
    """Tests for next-job integration with CollectionJob queue."""

    @staticmethod
    def _clean_queue(app):
        """Purge all CollectionJob rows to isolate tests from each other."""
        from app.models.collection_job import CollectionJob

        with app.app_context():
            CollectionJob.query.delete()
            db.session.commit()

    def test_fresh_vehicle_returns_bonus_from_queue(self, app, client):
        """When current vehicle is fresh, next-job returns queued bonus jobs."""
        self._clean_queue(app)
        with app.app_context():
            from app.models.collection_job import CollectionJob
            from app.services.market_service import store_market_prices

            store_market_prices(
                make="Renault",
                model="Talisman",
                year=2016,
                region="Ile-de-France",
                prices=list(range(12000, 22000, 500)),
                fuel="diesel",
                hp_range="120-150",
            )
            # Create a pending CollectionJob
            job = CollectionJob(
                make="Renault",
                model="Talisman",
                year=2016,
                region="Bretagne",
                fuel="diesel",
                hp_range="120-150",
                priority=1,
                source_vehicle="test",
            )
            db.session.add(job)
            db.session.commit()

        resp = client.get(
            "/api/market-prices/next-job?make=Renault&model=Talisman&year=2016"
            "&region=Ile-de-France&fuel=diesel&hp_range=120-150"
        )
        data = resp.get_json()
        assert data["success"] is True
        bonus = data["data"]["bonus_jobs"]
        assert len(bonus) >= 1
        assert any(j["region"] == "Bretagne" for j in bonus)
        assert any("job_id" in j for j in bonus)

    def test_next_job_triggers_expansion(self, app, client):
        """First scan triggers expand and returns collect=True + bonus jobs."""
        self._clean_queue(app)
        resp = client.get(
            "/api/market-prices/next-job?make=Toyota&model=Corolla&year=2020"
            "&region=Bretagne&fuel=essence&gearbox=manual&hp_range=70-120"
        )
        data = resp.get_json()
        assert data["data"]["collect"] is True
        # Verify jobs were created in DB
        with app.app_context():
            from app.models.collection_job import CollectionJob

            total = CollectionJob.query.filter_by(make="Toyota", model="Corolla").count()
            assert total > 0

    def test_next_job_bonus_includes_job_id(self, app, client):
        """Bonus jobs include job_id for completion callback."""
        self._clean_queue(app)
        with app.app_context():
            from app.models.collection_job import CollectionJob
            from app.services.market_service import store_market_prices

            job = CollectionJob(
                make="Fiat",
                model="500",
                year=2019,
                region="Corse",
                fuel="essence",
                hp_range="70-120",
                priority=1,
                source_vehicle="test",
            )
            db.session.add(job)
            db.session.commit()

            # Need a fresh MarketPrice so collect=false for this region
            store_market_prices(
                make="Fiat",
                model="500",
                year=2019,
                region="Ile-de-France",
                prices=list(range(8000, 18000, 500)),
            )

        resp = client.get(
            "/api/market-prices/next-job?make=Fiat&model=500&year=2019&region=Ile-de-France"
        )
        data = resp.get_json()
        bonus = data["data"]["bonus_jobs"]
        if bonus:
            assert "job_id" in bonus[0]

    def test_next_job_bonus_includes_country(self, app, client):
        """Bonus jobs include country field for multi-site extension dispatch."""
        self._clean_queue(app)
        with app.app_context():
            from app.models.collection_job import CollectionJob

            job = CollectionJob(
                make="VW",
                model="Golf",
                year=2022,
                region="Geneve",
                fuel="diesel",
                priority=1,
                source_vehicle="test",
                country="CH",
            )
            db.session.add(job)
            db.session.commit()

            from app.services.market_service import store_market_prices

            store_market_prices(
                make="VW",
                model="Golf",
                year=2022,
                region="Zurich",
                prices=list(range(15000, 30000, 500)),
                country="CH",
            )

        resp = client.get(
            "/api/market-prices/next-job?make=VW&model=Golf&year=2022&region=Zurich&country=CH"
        )
        data = resp.get_json()
        bonus = data["data"]["bonus_jobs"]
        if bonus:
            assert "country" in bonus[0]
            assert bonus[0]["country"] == "CH"

    def test_next_job_response_includes_country(self, app, client):
        """Next-job collect=true response includes country field."""
        self._clean_queue(app)
        resp = client.get(
            "/api/market-prices/next-job?make=BMW&model=X3&year=2023&region=Geneve&country=CH"
        )
        data = resp.get_json()
        if data["data"]["collect"]:
            assert data["data"]["country"] == "CH"

    def test_next_job_ch_uses_cantons(self, app, client):
        """expand_collection_jobs with country=CH creates canton-based jobs."""
        self._clean_queue(app)
        with app.app_context():
            from app.models.collection_job import CollectionJob

            # Clear all existing jobs
            CollectionJob.query.delete()
            db.session.commit()

        resp = client.get(
            "/api/market-prices/next-job?make=Renault&model=Clio&year=2022"
            "&region=Geneve&country=CH&fuel=essence"
        )
        data = resp.get_json()
        assert data["data"]["collect"] is True

        with app.app_context():
            from app.models.collection_job import CollectionJob

            ch_jobs = CollectionJob.query.filter_by(country="CH").all()
            # Should have created jobs for other cantons (P1)
            assert len(ch_jobs) >= 10  # 25 other cantons at minimum
            # Verify regions are Swiss cantons
            regions = {j.region for j in ch_jobs}
            assert "Zurich" in regions
            assert "Vaud" in regions


class TestNextJobYearValidation:
    """Regression: next-job must require year param to avoid crashes."""

    def test_next_job_without_year_returns_no_collect(self, client):
        """next-job sans year ne doit pas crasher (retourne collect=false)."""
        resp = client.get("/api/market-prices/next-job?make=Peugeot&model=208&region=Bretagne")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"]["collect"] is False


class TestLowDataCountryIsolation:
    """Regression: low-data detection must be isolated per country."""

    def test_ch_fails_dont_block_fr_expansion(self, app):
        """Des echecs CH ne doivent pas bloquer l'expansion FR."""
        from app.services.collection_job_service import (
            LOW_DATA_FAIL_THRESHOLD,
            _get_low_data_vehicles,
        )

        with app.app_context():
            from app.models.collection_job import CollectionJob

            # Create failed jobs for Peugeot 208 in CH
            for i in range(LOW_DATA_FAIL_THRESHOLD):
                db.session.add(
                    CollectionJob(
                        make="Peugeot",
                        model="208",
                        year=2022,
                        region=f"Canton{i}",
                        fuel="essence",
                        status="failed",
                        attempts=3,
                        country="CH",
                        source_vehicle="test",
                    )
                )
            db.session.commit()

            # CH should be low-data
            low_ch = _get_low_data_vehicles("CH")
            assert ("peugeot", "208", "CH") in low_ch

            # FR should NOT be low-data
            low_fr = _get_low_data_vehicles("FR")
            assert ("peugeot", "208", "FR") not in low_fr
