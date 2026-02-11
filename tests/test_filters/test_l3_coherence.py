"""Tests for L3 Coherence Filter."""

from app.filters.l3_coherence import L3CoherenceFilter


class TestL3CoherenceFilter:
    def setup_method(self):
        self.filt = L3CoherenceFilter()

    def test_coherent_data_passes(self):
        data = {
            "year_model": "2020",
            "mileage_km": 75000,
            "price_eur": 18000,
        }
        result = self.filt.run(data)
        assert result.status == "pass"
        assert result.score == 1.0

    def test_high_mileage_warns(self):
        data = {
            "year_model": "2022",
            "mileage_km": 150000,  # way too high for 2022
            "price_eur": 15000,
        }
        result = self.filt.run(data)
        assert result.status in ("warning", "fail")
        assert result.details["km_ratio"] > 1.5

    def test_low_mileage_warns(self):
        data = {
            "year_model": "2012",
            "mileage_km": 10000,  # suspiciously low for 14 years
            "price_eur": 8000,
        }
        result = self.filt.run(data)
        assert result.status == "warning"
        assert "bas" in result.message.lower()

    def test_future_year_fails(self):
        data = {
            "year_model": "2030",
            "mileage_km": 5000,
        }
        result = self.filt.run(data)
        assert result.status == "fail"
        assert "futur" in result.message.lower()

    def test_missing_year_skips(self):
        result = self.filt.run({"mileage_km": 50000})
        assert result.status == "skip"

    def test_missing_mileage_skips(self):
        result = self.filt.run({"year_model": "2020"})
        assert result.status == "skip"

    def test_very_low_price_warns(self):
        data = {
            "year_model": "2020",
            "mileage_km": 60000,
            "price_eur": 200,
        }
        result = self.filt.run(data)
        assert result.status in ("warning", "fail")
