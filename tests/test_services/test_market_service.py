"""Tests for market_service -- stockage et recuperation des prix du marche."""

from datetime import datetime, timedelta, timezone

from app.services.market_service import (
    _filter_outliers_iqr,
    get_market_stats,
    store_market_prices,
)


class TestStoreMarketPrices:
    """Tests de store_market_prices."""

    def test_creates_new_record(self, app):
        """store_market_prices cree un nouvel enregistrement."""
        with app.app_context():
            mp = store_market_prices(
                make="Peugeot",
                model="208",
                year=2021,
                region="Ile-de-France",
                prices=[12000, 13000, 14000, 15000, 16000],
            )
            assert mp.id is not None
            assert mp.make == "Peugeot"
            assert mp.model == "208"
            assert mp.year == 2021
            assert mp.region == "Ile-de-France"
            assert mp.sample_count == 5
            assert mp.price_min == 12000
            assert mp.price_max == 16000
            assert mp.price_median == 14000
            assert 13000 <= mp.price_mean <= 15000
            assert mp.price_std > 0

    def test_computes_stats_correctly(self, app):
        """Les statistiques sont calculees correctement."""
        with app.app_context():
            mp = store_market_prices(
                make="Renault",
                model="Clio",
                year=2020,
                region="Bretagne",
                prices=[10000, 10000, 10000],
            )
            assert mp.price_min == 10000
            assert mp.price_max == 10000
            assert mp.price_median == 10000
            assert mp.price_mean == 10000
            assert mp.price_std == 0.0

    def test_upserts_existing_record(self, app):
        """Un second appel met a jour l'enregistrement existant."""
        with app.app_context():
            mp1 = store_market_prices(
                make="Citroen",
                model="C3",
                year=2022,
                region="Normandie",
                prices=[8000, 9000, 10000],
            )
            first_id = mp1.id
            assert mp1.sample_count == 3

            mp2 = store_market_prices(
                make="Citroen",
                model="C3",
                year=2022,
                region="Normandie",
                prices=[8500, 9500, 10500, 11000, 12000],
            )
            assert mp2.id == first_id  # meme enregistrement
            assert mp2.sample_count == 5  # mis a jour

    def test_refresh_after_is_24h_later(self, app):
        """refresh_after est 24h apres collected_at."""
        with app.app_context():
            mp = store_market_prices(
                make="Toyota",
                model="Yaris",
                year=2023,
                region="PACA",
                prices=[11000, 12000, 13000],
            )
            delta = mp.refresh_after - mp.collected_at
            assert abs(delta.total_seconds() - 86400) < 2  # ~24h


class TestStoreWithFuel:
    """Tests de store_market_prices avec le parametre fuel."""

    def test_stores_fuel(self, app):
        """store_market_prices stocke le fuel normalise."""
        with app.app_context():
            mp = store_market_prices(
                make="Renault",
                model="Clio",
                year=2025,
                region="Ile-de-France",
                prices=[20000, 22000, 24000],
                fuel="Diesel",
            )
            assert mp.fuel == "diesel"

    def test_separate_records_per_fuel(self, app):
        """Deux appels avec fuel different creent deux enregistrements."""
        with app.app_context():
            mp1 = store_market_prices(
                make="Renault",
                model="Clio",
                year=2025,
                region="Bretagne",
                prices=[20000, 22000, 24000],
                fuel="diesel",
            )
            mp2 = store_market_prices(
                make="Renault",
                model="Clio",
                year=2025,
                region="Bretagne",
                prices=[18000, 19000, 20000],
                fuel="essence",
            )
            assert mp1.id != mp2.id
            assert mp1.fuel == "diesel"
            assert mp2.fuel == "essence"

    def test_upserts_same_fuel(self, app):
        """Deux appels avec meme fuel mettent a jour le meme enregistrement."""
        with app.app_context():
            mp1 = store_market_prices(
                make="Renault",
                model="Clio",
                year=2025,
                region="Corse",
                prices=[20000, 22000, 24000],
                fuel="diesel",
            )
            mp2 = store_market_prices(
                make="Renault",
                model="Clio",
                year=2025,
                region="Corse",
                prices=[21000, 23000, 25000],
                fuel="diesel",
            )
            assert mp1.id == mp2.id

    def test_no_fuel_separate_from_fuel(self, app):
        """Un enregistrement sans fuel et un avec fuel sont distincts."""
        with app.app_context():
            mp1 = store_market_prices(
                make="VW",
                model="Golf",
                year=2022,
                region="Grand Est",
                prices=[15000, 16000, 17000],
            )
            mp2 = store_market_prices(
                make="VW",
                model="Golf",
                year=2022,
                region="Grand Est",
                prices=[14000, 15000, 16000],
                fuel="essence",
            )
            assert mp1.id != mp2.id
            assert mp1.fuel is None
            assert mp2.fuel == "essence"


class TestGetMarketStats:
    """Tests de get_market_stats."""

    def test_returns_fresh_record(self, app):
        """get_market_stats retourne un enregistrement non expire."""
        with app.app_context():
            store_market_prices(
                make="BMW",
                model="Serie3",
                year=2020,
                region="Grand Est",
                prices=[25000, 27000, 29000],
            )
            result = get_market_stats("BMW", "Serie3", 2020, "Grand Est")
            assert result is not None
            assert result.price_median == 27000

    def test_returns_old_record(self, app):
        """get_market_stats retourne un enregistrement meme ancien (argus maison)."""
        from app.extensions import db

        with app.app_context():
            mp = store_market_prices(
                make="Audi",
                model="A3",
                year=2019,
                region="Hauts-de-France",
                prices=[20000, 22000, 24000],
            )
            # Donnees collectees il y a 30 jours -- toujours valable
            mp.refresh_after = datetime.now(timezone.utc) - timedelta(days=30)
            mp.collected_at = datetime.now(timezone.utc) - timedelta(days=31)
            db.session.commit()

            result = get_market_stats("Audi", "A3", 2019, "Hauts-de-France")
            assert result is not None
            assert result.price_median == 22000

    def test_returns_none_when_not_found(self, app):
        """get_market_stats retourne None quand aucun enregistrement n'existe."""
        with app.app_context():
            result = get_market_stats("Ferrari", "F40", 1990, "Corse")
            assert result is None

    def test_returns_fuel_match_first(self, app):
        """get_market_stats prefere le match avec fuel."""
        with app.app_context():
            store_market_prices(
                make="Renault",
                model="Clio",
                year=2025,
                region="Normandie",
                prices=[15000, 16000, 17000],
            )
            store_market_prices(
                make="Renault",
                model="Clio",
                year=2025,
                region="Normandie",
                prices=[20000, 22000, 24000],
                fuel="essence",
            )
            result = get_market_stats("Renault", "Clio", 2025, "Normandie", fuel="essence")
            assert result is not None
            assert result.fuel == "essence"
            assert result.price_median == 22000

    def test_falls_back_to_no_fuel(self, app):
        """get_market_stats tombe en fallback quand le fuel demande n'existe pas."""
        with app.app_context():
            store_market_prices(
                make="Fiat",
                model="500",
                year=2021,
                region="PACA",
                prices=[10000, 11000, 12000],
            )
            result = get_market_stats("Fiat", "500", 2021, "PACA", fuel="diesel")
            assert result is not None
            assert result.price_median == 11000

    def test_approx_year_with_fuel(self, app):
        """get_market_stats trouve une annee proche avec fuel match."""
        with app.app_context():
            store_market_prices(
                make="Toyota",
                model="Yaris",
                year=2022,
                region="Bretagne",
                prices=[14000, 15000, 16000],
                fuel="hybride",
            )
            result = get_market_stats("Toyota", "Yaris", 2023, "Bretagne", fuel="hybride")
            assert result is not None
            assert result.year == 2022
            assert result.fuel == "hybride"


class TestFilterOutliersIQR:
    """Tests du filtrage IQR des outliers."""

    def test_no_outliers_in_normal_data(self):
        """Donnees normales : rien n'est exclu."""
        prices = [15000, 16000, 17000, 18000, 19000]
        result = _filter_outliers_iqr(prices)
        assert len(result.excluded) == 0
        assert len(result.kept) == 5

    def test_excludes_extreme_low_outlier(self):
        """Un prix aberrant tres bas est exclu (ex: Mini 2023 a 2990)."""
        prices = [2990, 16000, 17000, 18000, 19000, 20000, 22000]
        result = _filter_outliers_iqr(prices)
        assert 2990 in result.excluded
        assert 2990 not in result.kept
        assert len(result.kept) >= 5

    def test_excludes_extreme_high_outlier(self):
        """Un prix aberrant tres haut est exclu."""
        prices = [15000, 16000, 17000, 18000, 19000, 95000]
        result = _filter_outliers_iqr(prices)
        assert 95000 in result.excluded
        assert 95000 not in result.kept

    def test_keeps_all_if_too_few_after_filter(self):
        """Si le filtrage enleverait trop de donnees, on garde tout."""
        prices = [500, 1000, 50000]  # Tout est outlier par rapport aux autres
        result = _filter_outliers_iqr(prices)
        # Doit garder au moins IQR_MIN_KEEP (3) → garde tout
        assert len(result.kept) == 3
        assert len(result.excluded) == 0

    def test_identical_prices_no_exclusion(self):
        """Prix identiques : IQR=0, tout est garde."""
        prices = [10000, 10000, 10000, 10000]
        result = _filter_outliers_iqr(prices)
        assert len(result.kept) == 4
        assert len(result.excluded) == 0

    def test_real_mini_scenario(self):
        """Scenario reel Mini 2023 : l'outlier a 2990 casse la moyenne."""
        # Donnees reelles du user
        prices = [2990, 16980, 17000, 17500, 18000, 19000, 44970]
        result = _filter_outliers_iqr(prices)
        # 2990 et/ou 44970 devraient etre exclus
        assert 2990 in result.excluded or 44970 in result.excluded
        import numpy as np

        # La mediane des prix gardes devrait etre plus representative
        arr_kept = np.array(result.kept, dtype=float)
        assert 15000 <= int(np.median(arr_kept)) <= 25000


class TestIQRMean:
    """Tests du calcul IQR Mean (Moyenne Interquartile)."""

    def test_iqr_mean_with_uniform_prices(self):
        """IQR Mean sur prix uniformes = la valeur elle-meme."""
        prices = [10000, 10000, 10000, 10000, 10000]
        result = _filter_outliers_iqr(prices)
        assert result.iqr_mean == 10000

    def test_iqr_mean_is_between_q1_and_q3(self):
        """IQR Mean doit etre entre Q1 et Q3."""
        prices = [10000, 12000, 14000, 16000, 18000, 20000, 22000, 24000]
        result = _filter_outliers_iqr(prices)
        assert result.q1 <= result.iqr_mean <= result.q3

    def test_iqr_mean_more_robust_than_mean(self):
        """IQR Mean resiste mieux aux outliers que la moyenne classique."""
        import numpy as np

        prices = [2990, 16000, 17000, 18000, 19000, 20000, 44970]
        result = _filter_outliers_iqr(prices)
        # La moyenne classique des prix gardes
        classic_mean = float(np.mean(result.kept))
        # L'IQR Mean ne doit pas etre tiree par les extremes gardes
        assert (
            abs(result.iqr_mean - 18000) < abs(classic_mean - 18000)
            or abs(result.iqr_mean - classic_mean) < 1000
        )

    def test_iqr_mean_symmetric_distribution(self):
        """Sur une distribution symetrique, IQR Mean ≈ mediane."""
        prices = [10000, 12000, 14000, 16000, 18000, 20000, 22000]
        result = _filter_outliers_iqr(prices)
        import numpy as np

        median = float(np.median(result.kept))
        # Avec une distribution symetrique, l'ecart devrait etre faible
        assert abs(result.iqr_mean - median) < 2000

    def test_iqr_mean_skewed_distribution(self):
        """Sur une distribution asymetrique, IQR Mean capture mieux le centre."""
        # Distribution avec queue vers le haut
        prices = [15000, 16000, 17000, 17500, 18000, 18500, 19000, 25000, 28000]
        result = _filter_outliers_iqr(prices)
        # IQR Mean devrait etre dans la zone centrale
        assert 16000 <= result.iqr_mean <= 20000

    def test_iqr_result_has_q1_q3(self):
        """IQRResult expose Q1 et Q3."""
        prices = [10000, 12000, 14000, 16000, 18000, 20000]
        result = _filter_outliers_iqr(prices)
        assert result.q1 > 0
        assert result.q3 > result.q1
        assert result.iqr_low <= result.q1
        assert result.iqr_high >= result.q3

    def test_iqr_mean_with_three_prices(self):
        """IQR Mean fonctionne avec le minimum de 3 prix."""
        prices = [10000, 15000, 20000]
        result = _filter_outliers_iqr(prices)
        assert result.iqr_mean > 0
        assert 10000 <= result.iqr_mean <= 20000


class TestStoreWithIQR:
    """Tests que store_market_prices utilise bien le filtrage IQR."""

    def test_stores_calculation_details(self, app):
        """Les details du calcul sont stockes en JSON."""
        with app.app_context():
            mp = store_market_prices(
                make="Mini",
                model="Autres",
                year=2023,
                region="Bourgogne",
                prices=[2990, 16980, 17000, 17500, 18000, 19000, 44970],
            )
            details = mp.get_calculation_details()
            assert details is not None
            assert details["method"] == "iqr_mean"
            assert details["raw_count"] == 7
            assert details["kept_count"] <= 7
            assert details["excluded_count"] >= 1
            assert 2990 in details["raw_prices"]

    def test_stores_price_details(self, app):
        """Les price_details (year, km, fuel) sont stockes dans calculation_details."""
        with app.app_context():
            price_details = [
                {"price": 16000, "year": 2022, "km": 45000, "fuel": "Diesel"},
                {"price": 17000, "year": 2021, "km": 60000, "fuel": "Diesel"},
                {"price": 18000, "year": 2023, "km": 30000, "fuel": "Essence"},
                {"price": 19000, "year": 2022, "km": 50000, "fuel": "Diesel"},
                {"price": 20000, "year": 2021, "km": 55000, "fuel": "Essence"},
            ]
            mp = store_market_prices(
                make="TestDetails",
                model="WithDetails",
                year=2022,
                region="TestRegion",
                prices=[16000, 17000, 18000, 19000, 20000],
                price_details=price_details,
            )
            details = mp.get_calculation_details()
            assert details is not None
            assert details["kept_details"] is not None
            assert len(details["kept_details"]) == 5
            # Chaque element doit avoir price, year, km, fuel
            first = details["kept_details"][0]
            assert "price" in first
            assert "year" in first
            assert "km" in first
            assert "fuel" in first

    def test_no_price_details_keeps_none(self, app):
        """Sans price_details, kept_details et excluded_details sont None."""
        with app.app_context():
            mp = store_market_prices(
                make="TestNoDetails",
                model="WithoutDetails",
                year=2022,
                region="TestRegion",
                prices=[16000, 17000, 18000, 19000, 20000],
            )
            details = mp.get_calculation_details()
            assert details is not None
            assert details["kept_details"] is None
            assert details["excluded_details"] is None

    def test_outlier_excluded_from_stats(self, app):
        """Les stats sont calculees sur les prix filtres, pas les bruts."""
        with app.app_context():
            mp = store_market_prices(
                make="MiniTest",
                model="OutlierTest",
                year=2023,
                region="Test",
                prices=[2990, 16000, 17000, 18000, 19000, 20000],
            )
            # Si 2990 est exclu, le min devrait etre >= 16000
            assert mp.price_min >= 15000
            # La moyenne devrait etre > 16000 (pas tiree vers le bas par 2990)
            assert mp.price_mean >= 16000

    def test_stores_iqr_mean_and_percentiles(self, app):
        """store_market_prices stocke price_iqr_mean, price_p25 et price_p75."""
        with app.app_context():
            mp = store_market_prices(
                make="TestIQR",
                model="Percentiles",
                year=2024,
                region="TestRegion",
                prices=[10000, 12000, 14000, 16000, 18000, 20000, 22000, 24000],
            )
            assert mp.price_iqr_mean is not None
            assert mp.price_p25 is not None
            assert mp.price_p75 is not None
            # P25 < IQR Mean < P75
            assert mp.price_p25 <= mp.price_iqr_mean <= mp.price_p75
            # IQR Mean dans les bornes raisonnables
            assert mp.price_min <= mp.price_iqr_mean <= mp.price_max
            # Details doivent contenir iqr_mean
            details = mp.get_calculation_details()
            assert details["iqr_mean"] > 0
            assert details["precision"] is None  # pas de precision fournie

    def test_stores_precision(self, app):
        """store_market_prices stocke la precision dans le record et les details."""
        with app.app_context():
            mp = store_market_prices(
                make="TestPrec",
                model="WithPrecision",
                year=2024,
                region="TestRegion",
                prices=[10000, 12000, 14000, 16000, 18000],
                precision=4,
            )
            assert mp.precision == 4
            details = mp.get_calculation_details()
            assert details["precision"] == 4

    def test_stores_search_log(self, app):
        """store_market_prices persiste le search_log dans calculation_details."""
        with app.app_context():
            search_log = [
                {
                    "step": 1,
                    "precision": 4,
                    "location_type": "region",
                    "year_spread": 1,
                    "filters_applied": ["fuel"],
                    "ads_found": 5,
                    "url": "https://www.leboncoin.fr/recherche?test=1",
                    "was_selected": False,
                    "reason": "5 < 20",
                },
                {
                    "step": 2,
                    "precision": 3,
                    "location_type": "national",
                    "year_spread": 2,
                    "filters_applied": ["fuel"],
                    "ads_found": 22,
                    "url": "https://www.leboncoin.fr/recherche?test=2",
                    "was_selected": True,
                    "reason": "22 >= 20",
                },
            ]
            mp = store_market_prices(
                make="Ford",
                model="Focus",
                year=2020,
                region="Normandie",
                prices=[10000, 11000, 12000, 13000, 14000],
                search_log=search_log,
            )
            details = mp.get_calculation_details()
            assert details["search_steps"] is not None
            assert len(details["search_steps"]) == 2
            assert details["search_steps"][1]["was_selected"] is True
            assert details["search_steps"][0]["ads_found"] == 5

    def test_stores_none_search_log_when_absent(self, app):
        """Sans search_log, search_steps est None (backward-compat)."""
        with app.app_context():
            mp = store_market_prices(
                make="Ford",
                model="Fiesta",
                year=2019,
                region="Bretagne",
                prices=[8000, 9000, 10000, 11000, 12000],
            )
            details = mp.get_calculation_details()
            assert details.get("search_steps") is None
