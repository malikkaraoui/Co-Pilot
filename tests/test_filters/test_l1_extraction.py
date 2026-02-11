"""Tests for L1 Extraction Quality Filter."""

from app.filters.l1_extraction import L1ExtractionFilter


class TestL1ExtractionFilter:
    def setup_method(self):
        self.filt = L1ExtractionFilter()

    def test_complete_data_passes(self):
        data = {
            "price_eur": 18500,
            "make": "Peugeot",
            "model": "3008",
            "year_model": "2019",
            "mileage_km": 75000,
            "fuel": "Diesel",
            "gearbox": "Manuelle",
            "phone": "0612345678",
            "color": "Gris",
            "location": {"city": "Lyon"},
        }
        result = self.filt.run(data)
        assert result.status == "pass"
        assert result.score == 1.0

    def test_missing_secondary_gives_warning(self):
        data = {
            "price_eur": 18500,
            "make": "Peugeot",
            "model": "3008",
            "year_model": "2019",
            "mileage_km": 75000,
            # missing: fuel, gearbox, phone, color, location
        }
        result = self.filt.run(data)
        assert result.status == "warning"
        assert result.score == 0.5
        assert "secondaires" in result.message

    def test_missing_critical_gives_warning_or_fail(self):
        data = {
            "price_eur": 18500,
            "make": "Peugeot",
            # missing: model, year_model, mileage_km
        }
        result = self.filt.run(data)
        assert result.status in ("warning", "fail")
        assert len(result.details["missing_critical"]) >= 2

    def test_empty_data_fails(self):
        result = self.filt.run({})
        assert result.status == "fail"
        assert result.score == 0.0
        assert len(result.details["missing_critical"]) == 5

    def test_filter_id(self):
        assert self.filt.filter_id == "L1"
