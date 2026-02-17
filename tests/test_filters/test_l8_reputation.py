"""Tests for L8 Import Detection Filter."""

from app.filters.l8_reputation import L8ImportDetectionFilter


class TestL8ImportDetectionFilter:
    def setup_method(self):
        self.filt = L8ImportDetectionFilter()

    def test_clean_ad_passes(self):
        data = {
            "phone": "0612345678",
            "description": "Vehicule en excellent etat, revision complete.",
            "price_eur": 18000,
            "year_model": "2020",
            "owner_type": "private",
        }
        result = self.filt.run(data)
        assert result.status == "pass"
        assert result.score == 1.0

    def test_foreign_phone_warns(self):
        data = {
            "phone": "+48612345678",
            "description": "Belle voiture.",
            "price_eur": 18000,
            "year_model": "2020",
        }
        result = self.filt.run(data)
        assert result.status == "warning"
        assert len(result.details["signals"]) == 1

    def test_import_keywords_warns(self):
        data = {
            "description": "Vehicule importé, carnet entretien complet.",
            "price_eur": 18000,
            "year_model": "2020",
        }
        result = self.filt.run(data)
        assert result.status == "warning"
        assert any("import" in s.lower() for s in result.details["signals"])

    def test_import_keyword_and_country_fails(self):
        data = {
            "description": "Vehicule importé d'Allemagne, carnet entretien complet.",
            "price_eur": 18000,
            "year_model": "2020",
        }
        result = self.filt.run(data)
        assert result.status == "fail"
        assert len(result.details["signals"]) >= 2
        assert any("import" in s.lower() for s in result.details["signals"])
        assert any("allemagne" in s.lower() for s in result.details["signals"])

    def test_multiple_signals_fails(self):
        data = {
            "phone": "+49612345678",
            "description": "Importée d'Allemagne, excellent prix.",
            "price_eur": 2000,
            "year_model": "2022",
        }
        result = self.filt.run(data)
        assert result.status == "fail"
        assert len(result.details["signals"]) >= 2

    def test_pro_without_siret_warns(self):
        data = {
            "owner_type": "pro",
            "siret": None,
            "description": "Vehicule de flotte.",
            "price_eur": 15000,
            "year_model": "2019",
        }
        result = self.filt.run(data)
        assert result.status == "warning"
        assert any("SIRET" in s for s in result.details["signals"])

    def test_empty_data_passes(self):
        result = self.filt.run({})
        assert result.status == "pass"
