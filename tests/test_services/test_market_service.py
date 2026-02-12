"""Tests for market_service -- stockage et recuperation des prix du marche."""

from datetime import datetime, timedelta, timezone

from app.services.market_service import get_market_stats, store_market_prices


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
