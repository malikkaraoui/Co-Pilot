"""Tests for L5 Visual/NumPy Filter."""

from unittest.mock import patch

import numpy as np

from app.filters.l5_visual import L5VisualFilter
from app.models.vehicle import Vehicle


class TestL5VisualFilter:
    def setup_method(self):
        self.filt = L5VisualFilter()
        self.vehicle = Vehicle(id=1, brand="Peugeot", model="3008")

    def _make_ref_array(self, prices):
        return np.array(prices, dtype=float)

    def test_normal_price_passes(self):
        ref = self._make_ref_array([17000, 18000, 19000, 17500, 18500])
        with (
            patch.object(L5VisualFilter, "_collect_market_prices", return_value=None),
            patch("app.services.vehicle_lookup.find_vehicle", return_value=self.vehicle),
            patch.object(L5VisualFilter, "_collect_argus_prices", return_value=ref),
        ):
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
        ref = self._make_ref_array([17000, 18000, 19000, 17500, 18500])
        with (
            patch.object(L5VisualFilter, "_collect_market_prices", return_value=None),
            patch("app.services.vehicle_lookup.find_vehicle", return_value=self.vehicle),
            patch.object(L5VisualFilter, "_collect_argus_prices", return_value=ref),
        ):
            result = self.filt.run(
                {
                    "price_eur": 5000,  # way below
                    "make": "Peugeot",
                    "model": "3008",
                }
            )
        assert result.status in ("warning", "fail")

    def test_not_enough_data_skips(self):
        ref = self._make_ref_array([17000])
        with (
            patch.object(L5VisualFilter, "_collect_market_prices", return_value=None),
            patch("app.services.vehicle_lookup.find_vehicle", return_value=self.vehicle),
            patch.object(L5VisualFilter, "_collect_argus_prices", return_value=ref),
        ):
            result = self.filt.run(
                {
                    "price_eur": 18000,
                    "make": "Peugeot",
                    "model": "3008",
                }
            )
        assert result.status == "skip"

    def test_no_vehicle_no_market_skips(self):
        with (
            patch.object(L5VisualFilter, "_collect_market_prices", return_value=None),
            patch("app.services.vehicle_lookup.find_vehicle", return_value=None),
        ):
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
        market_ref = np.array([15000, 18000, 21000], dtype=float)

        with patch.object(L5VisualFilter, "_collect_market_prices", return_value=market_ref):
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

    def test_market_price_works_without_vehicle_referentiel(self):
        """L5 utilise MarketPrice meme si le vehicule n'est pas dans le referentiel."""
        market_ref = np.array([55000, 60000, 65000, 58000, 62000], dtype=float)

        with (
            patch.object(L5VisualFilter, "_collect_market_prices", return_value=market_ref),
            patch("app.services.vehicle_lookup.find_vehicle", return_value=None),
        ):
            result = self.filt.run(
                {
                    "price_eur": 59900,
                    "make": "Porsche",
                    "model": "Cayenne",
                    "year_model": "2019",
                    "location": {"region": "Haute-Normandie"},
                }
            )

        assert result.status == "pass"
        assert result.details["source"] == "marche_leboncoin"
