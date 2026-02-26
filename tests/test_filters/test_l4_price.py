"""Tests for L4 Price/Argus Filter."""

from unittest.mock import patch

from app.filters.l4_price import L4PriceFilter
from app.models.argus import ArgusPrice
from app.models.vehicle import Vehicle
from app.services.market_service import store_market_prices


class TestL4PriceFilter:
    def setup_method(self):
        self.filt = L4PriceFilter()
        self.vehicle = Vehicle(id=1, brand="Peugeot", model="3008")
        self.argus = ArgusPrice(
            vehicle_id=1,
            region="Auvergne-Rhone-Alpes",
            year=2019,
            price_low=15000,
            price_mid=18000,
            price_high=21000,
        )

    def _base_data(self, price=18500):
        return {
            "price_eur": price,
            "make": "Peugeot",
            "model": "3008",
            "year_model": "2019",
            "location": {"region": "Auvergne-Rhone-Alpes"},
        }

    def test_price_in_range_passes(self):
        with (
            patch("app.services.vehicle_lookup.find_vehicle", return_value=self.vehicle),
            patch("app.services.market_service.get_market_stats", return_value=None),
            patch("app.services.argus.get_argus_price", return_value=self.argus),
        ):
            result = self.filt.run(self._base_data(18500))
        assert result.status == "pass"
        assert abs(result.details["delta_pct"]) <= 10
        assert result.details["source"] == "argus_seed"

    def test_price_above_warns(self):
        with (
            patch("app.services.vehicle_lookup.find_vehicle", return_value=self.vehicle),
            patch("app.services.market_service.get_market_stats", return_value=None),
            patch("app.services.argus.get_argus_price", return_value=self.argus),
        ):
            result = self.filt.run(self._base_data(22000))
        assert result.status == "warning"
        assert "au-dessus" in result.message

    def test_price_way_below_fails(self):
        with (
            patch("app.services.vehicle_lookup.find_vehicle", return_value=self.vehicle),
            patch("app.services.market_service.get_market_stats", return_value=None),
            patch("app.services.argus.get_argus_price", return_value=self.argus),
        ):
            result = self.filt.run(self._base_data(10000))
        assert result.status == "fail"
        assert "anomalie" in result.message.lower()

    def test_no_price_skips(self):
        result = self.filt.run({"make": "Peugeot", "model": "3008"})
        assert result.status == "skip"

    def test_no_vehicle_no_market_skips(self):
        with (
            patch("app.services.market_service.get_market_stats", return_value=None),
            patch("app.services.vehicle_lookup.find_vehicle", return_value=None),
        ):
            result = self.filt.run(self._base_data())
        assert result.status == "skip"

    def test_no_argus_skips(self):
        with (
            patch("app.services.vehicle_lookup.find_vehicle", return_value=self.vehicle),
            patch("app.services.market_service.get_market_stats", return_value=None),
            patch("app.services.argus.get_argus_price", return_value=None),
        ):
            result = self.filt.run(self._base_data())
        assert result.status == "skip"

    def test_skip_contains_lookup_diagnostics(self):
        with (
            patch("app.services.vehicle_lookup.find_vehicle", return_value=None),
            patch("app.services.market_service.get_market_stats", return_value=None),
        ):
            result = self.filt.run(self._base_data())
        assert result.status == "skip"
        assert result.details is not None
        assert result.details.get("lookup_make") == "Peugeot"
        assert result.details.get("lookup_model") == "3008"
        assert result.details.get("lookup_region_key") is not None

    def test_stale_below_market_warns(self):
        """Prix en dessous de la ref + >30 jours = signal anguille sous roche."""
        data = self._base_data(13000)
        data["days_online"] = 45
        with (
            patch("app.services.vehicle_lookup.find_vehicle", return_value=self.vehicle),
            patch("app.services.market_service.get_market_stats", return_value=None),
            patch("app.services.argus.get_argus_price", return_value=self.argus),
        ):
            result = self.filt.run(data)
        assert result.details.get("stale_below_market") is True
        assert "45 jours" in result.message
        assert "acheteurs" in result.message

    def test_recent_below_market_no_stale_signal(self):
        """Prix en dessous de la ref mais annonce recente = pas de signal stale."""
        data = self._base_data(13000)
        data["days_online"] = 5
        with (
            patch("app.services.vehicle_lookup.find_vehicle", return_value=self.vehicle),
            patch("app.services.market_service.get_market_stats", return_value=None),
            patch("app.services.argus.get_argus_price", return_value=self.argus),
        ):
            result = self.filt.run(data)
        assert "stale_below_market" not in result.details

    def test_stale_above_market_no_stale_signal(self):
        """Prix au-dessus de la ref + >30 jours = pas de signal anguille."""
        data = self._base_data(22000)
        data["days_online"] = 45
        with (
            patch("app.services.vehicle_lookup.find_vehicle", return_value=self.vehicle),
            patch("app.services.market_service.get_market_stats", return_value=None),
            patch("app.services.argus.get_argus_price", return_value=self.argus),
        ):
            result = self.filt.run(data)
        assert "stale_below_market" not in result.details


class TestL4MarketPriceFallback:
    """Tests du fallback MarketPrice -> ArgusPrice dans L4."""

    def setup_method(self):
        self.filt = L4PriceFilter()
        self.vehicle = Vehicle(id=1, brand="Peugeot", model="3008")

    def _base_data(self, price=18500):
        return {
            "price_eur": price,
            "make": "Peugeot",
            "model": "3008",
            "year_model": "2019",
            "location": {"region": "Auvergne-Rhone-Alpes"},
        }

    def test_uses_market_price_when_available(self):
        """L4 utilise MarketPrice quand disponible avec assez de samples."""
        from unittest.mock import MagicMock

        market = MagicMock()
        market.price_iqr_mean = 17500
        market.price_median = 17500
        market.price_p25 = 16000
        market.price_p75 = 19000
        market.sample_count = 10
        market.precision = 4

        with (
            patch("app.services.vehicle_lookup.find_vehicle", return_value=self.vehicle),
            patch("app.services.market_service.get_market_stats", return_value=market),
        ):
            result = self.filt.run(self._base_data(18000))

        assert result.status == "pass"
        assert result.details["source"] == "marche_leboncoin"
        assert result.details["sample_count"] == 10

    def test_falls_back_to_argus_when_market_insufficient(self):
        """L4 retombe sur ArgusPrice quand MarketPrice a trop peu de samples."""
        from unittest.mock import MagicMock

        market = MagicMock()
        market.sample_count = 2  # < MARKET_MIN_SAMPLES (3), insuffisant

        argus = ArgusPrice(
            vehicle_id=1,
            region="Auvergne-Rhone-Alpes",
            year=2019,
            price_low=15000,
            price_mid=18000,
            price_high=21000,
        )

        with (
            patch("app.services.vehicle_lookup.find_vehicle", return_value=self.vehicle),
            patch("app.services.market_service.get_market_stats", return_value=market),
            patch("app.services.argus.get_argus_price", return_value=argus),
        ):
            result = self.filt.run(self._base_data(18500))

        assert result.status == "pass"
        assert result.details["source"] == "argus_seed"

    def test_market_price_works_without_vehicle_referentiel(self):
        """L4 utilise MarketPrice meme si le vehicule n'est pas dans le referentiel."""
        from unittest.mock import MagicMock

        market = MagicMock()
        market.price_iqr_mean = 60000
        market.price_median = 60000
        market.price_p25 = 55000
        market.price_p75 = 65000
        market.sample_count = 33
        market.precision = 3

        # find_vehicle retourne None (pas dans le referentiel)
        # mais MarketPrice existe quand meme
        with (
            patch("app.services.market_service.get_market_stats", return_value=market),
            patch("app.services.vehicle_lookup.find_vehicle", return_value=None),
        ):
            data = {
                "price_eur": 59900,
                "make": "Porsche",
                "model": "Cayenne",
                "year_model": "2019",
                "location": {"region": "Haute-Normandie"},
            }
            result = self.filt.run(data)

        assert result.status == "pass"
        assert result.details["source"] == "marche_leboncoin"
        assert result.details["sample_count"] == 33


class TestL4FuelAccentIntegration:
    """Tests d'integration L4 pour les carburants accentues (Électrique, etc.)."""

    def test_l4_uses_market_price_with_accented_fuel(self, app):
        """Un fuel accentue dans l'annonce doit retrouver le MarketPrice stocke sans accent."""
        with app.app_context():
            store_market_prices(
                make="Hyundai",
                model="Kona",
                year=2022,
                region="Languedoc-Roussillon",
                prices=[13299, 13990, 14480, 14990, 17900],
                fuel="electrique",
                precision=4,
            )

            filt = L4PriceFilter()
            result = filt.run(
                {
                    "price_eur": 14480,
                    "make": "Hyundai",
                    "model": "Kona",
                    "year_model": "2022",
                    "fuel": "Électrique",
                    "location": {"region": "Languedoc-Roussillon"},
                }
            )

        assert result.status in {"pass", "warning"}
        assert result.details["source"] == "marche_leboncoin"
        assert result.details["sample_count"] >= 3
