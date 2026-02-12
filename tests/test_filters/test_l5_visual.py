"""Tests for L5 Visual/NumPy Filter."""

from unittest.mock import MagicMock, patch

from app.filters.l5_visual import L5VisualFilter
from app.models.argus import ArgusPrice
from app.models.market_price import MarketPrice
from app.models.vehicle import Vehicle


class TestL5VisualFilter:
    def setup_method(self):
        self.filt = L5VisualFilter()
        self.vehicle = Vehicle(id=1, brand="Peugeot", model="3008")

    def _make_argus_records(self, prices):
        return [ArgusPrice(vehicle_id=1, region="R", year=2019, price_mid=p) for p in prices]

    def test_normal_price_passes(self):
        records = self._make_argus_records([17000, 18000, 19000, 17500, 18500])
        with (
            patch("app.services.vehicle_lookup.find_vehicle", return_value=self.vehicle),
            patch.object(MarketPrice, "query") as mock_mq,
            patch.object(ArgusPrice, "query") as mock_q,
        ):
            mock_mq.filter.return_value.all.return_value = []
            mock_q.filter_by.return_value.all.return_value = records
            result = self.filt.run(
                {
                    "price_eur": 18000,
                    "make": "Peugeot",
                    "model": "3008",
                }
            )
        assert result.status == "pass"
        assert result.details["source"] == "argus_seed"

    def test_outlier_price_fails(self):
        records = self._make_argus_records([17000, 18000, 19000, 17500, 18500])
        with (
            patch("app.services.vehicle_lookup.find_vehicle", return_value=self.vehicle),
            patch.object(MarketPrice, "query") as mock_mq,
            patch.object(ArgusPrice, "query") as mock_q,
        ):
            mock_mq.filter.return_value.all.return_value = []
            mock_q.filter_by.return_value.all.return_value = records
            result = self.filt.run(
                {
                    "price_eur": 5000,  # way below
                    "make": "Peugeot",
                    "model": "3008",
                }
            )
        assert result.status in ("warning", "fail")

    def test_not_enough_data_skips(self):
        records = self._make_argus_records([17000])
        with (
            patch("app.services.vehicle_lookup.find_vehicle", return_value=self.vehicle),
            patch.object(MarketPrice, "query") as mock_mq,
            patch.object(ArgusPrice, "query") as mock_q,
        ):
            mock_mq.filter.return_value.all.return_value = []
            mock_q.filter_by.return_value.all.return_value = records
            result = self.filt.run(
                {
                    "price_eur": 18000,
                    "make": "Peugeot",
                    "model": "3008",
                }
            )
        assert result.status == "skip"

    def test_no_vehicle_skips(self):
        with patch("app.services.vehicle_lookup.find_vehicle", return_value=None):
            result = self.filt.run(
                {
                    "price_eur": 18000,
                    "make": "Unknown",
                    "model": "Car",
                }
            )
        assert result.status == "skip"

    def test_no_make_model_skips(self):
        result = self.filt.run({"price_eur": 18000})
        assert result.status == "skip"


class TestL5MarketPriceFallback:
    """Tests du fallback MarketPrice -> ArgusPrice dans L5."""

    def setup_method(self):
        self.filt = L5VisualFilter()
        self.vehicle = Vehicle(id=1, brand="Peugeot", model="3008")

    def test_uses_market_price_when_available(self):
        """L5 utilise MarketPrice quand disponible avec assez de samples."""
        mp1 = MagicMock(spec=MarketPrice)
        mp1.price_min = 15000
        mp1.price_median = 18000
        mp1.price_max = 21000
        mp1.sample_count = 10

        with (
            patch("app.services.vehicle_lookup.find_vehicle", return_value=self.vehicle),
            patch.object(MarketPrice, "query") as mock_mq,
        ):
            mock_mq.filter.return_value.all.return_value = [mp1]
            result = self.filt.run(
                {
                    "price_eur": 18000,
                    "make": "Peugeot",
                    "model": "3008",
                    "year_model": "2019",
                    "location": {"region": "Auvergne-Rhone-Alpes"},
                }
            )

        assert result.status == "pass"
        assert result.details["source"] == "marche_leboncoin"
