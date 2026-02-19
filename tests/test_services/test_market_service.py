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
        kept, excluded, _, _ = _filter_outliers_iqr(prices)
        assert len(excluded) == 0
        assert len(kept) == 5

    def test_excludes_extreme_low_outlier(self):
        """Un prix aberrant tres bas est exclu (ex: Mini 2023 a 2990)."""
        prices = [2990, 16000, 17000, 18000, 19000, 20000, 22000]
        kept, excluded, _, _ = _filter_outliers_iqr(prices)
        assert 2990 in excluded
        assert 2990 not in kept
        assert len(kept) >= 5

    def test_excludes_extreme_high_outlier(self):
        """Un prix aberrant tres haut est exclu."""
        prices = [15000, 16000, 17000, 18000, 19000, 95000]
        kept, excluded, _, _ = _filter_outliers_iqr(prices)
        assert 95000 in excluded
        assert 95000 not in kept

    def test_keeps_all_if_too_few_after_filter(self):
        """Si le filtrage enleverait trop de donnees, on garde tout."""
        prices = [500, 1000, 50000]  # Tout est outlier par rapport aux autres
        kept, excluded, _, _ = _filter_outliers_iqr(prices)
        # Doit garder au moins IQR_MIN_KEEP (3) → garde tout
        assert len(kept) == 3
        assert len(excluded) == 0

    def test_identical_prices_no_exclusion(self):
        """Prix identiques : IQR=0, tout est garde."""
        prices = [10000, 10000, 10000, 10000]
        kept, excluded, _, _ = _filter_outliers_iqr(prices)
        assert len(kept) == 4
        assert len(excluded) == 0

    def test_real_mini_scenario(self):
        """Scenario reel Mini 2023 : l'outlier a 2990 casse la moyenne."""
        # Donnees reelles du user
        prices = [2990, 16980, 17000, 17500, 18000, 19000, 44970]
        kept, excluded, _, _ = _filter_outliers_iqr(prices)
        # 2990 et/ou 44970 devraient etre exclus
        assert 2990 in excluded or 44970 in excluded
        import numpy as np

        # La mediane des prix gardes devrait etre plus representative
        arr_kept = np.array(kept, dtype=float)
        assert 15000 <= int(np.median(arr_kept)) <= 25000


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
            assert details["method"] == "iqr"
            assert details["raw_count"] == 7
            assert details["kept_count"] <= 7
            assert details["excluded_count"] >= 1
            assert 2990 in details["raw_prices"]

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
