"""Tests for L4 Price/Argus Filter."""

from unittest.mock import patch

from app.filters.l4_price import L4PriceFilter
from app.models.argus import ArgusPrice
from app.models.vehicle import Vehicle


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
            patch("app.services.argus.get_argus_price", return_value=self.argus),
        ):
            result = self.filt.run(self._base_data(18500))
        assert result.status == "pass"
        assert abs(result.details["delta_pct"]) <= 10

    def test_price_above_warns(self):
        with (
            patch("app.services.vehicle_lookup.find_vehicle", return_value=self.vehicle),
            patch("app.services.argus.get_argus_price", return_value=self.argus),
        ):
            result = self.filt.run(self._base_data(22000))
        assert result.status == "warning"
        assert "au-dessus" in result.message

    def test_price_way_below_fails(self):
        with (
            patch("app.services.vehicle_lookup.find_vehicle", return_value=self.vehicle),
            patch("app.services.argus.get_argus_price", return_value=self.argus),
        ):
            result = self.filt.run(self._base_data(10000))
        assert result.status == "fail"
        assert "anomalie" in result.message.lower()

    def test_no_price_skips(self):
        result = self.filt.run({"make": "Peugeot", "model": "3008"})
        assert result.status == "skip"

    def test_no_vehicle_skips(self):
        with patch("app.services.vehicle_lookup.find_vehicle", return_value=None):
            result = self.filt.run(self._base_data())
        assert result.status == "skip"

    def test_no_argus_skips(self):
        with (
            patch("app.services.vehicle_lookup.find_vehicle", return_value=self.vehicle),
            patch("app.services.argus.get_argus_price", return_value=None),
        ):
            result = self.filt.run(self._base_data())
        assert result.status == "skip"
