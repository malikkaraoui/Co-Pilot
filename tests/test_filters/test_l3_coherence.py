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

    def test_recent_low_km_pro_immatriculation_constructeur(self):
        """Vehicule de 1 an, 10 km, pro → immatriculation constructeur, pas compteur trafique."""
        data = {
            "year_model": "2025",
            "mileage_km": 10,
            "price_eur": 28000,
            "owner_type": "pro",
            "make": "Peugeot",
            "model": "308",
        }
        result = self.filt.run(data)
        assert result.status == "warning"
        assert result.score == 0.7  # informatif, pas alarmant
        assert "immatriculation constructeur" in result.message
        assert "compteur" not in result.message.lower()
        assert result.details["is_recent_low_km"] is True

    def test_recent_low_km_private_not_found_buyer(self):
        """Vehicule de 1 an, 500 km, particulier → n'a pas trouve preneur."""
        data = {
            "year_model": "2025",
            "mileage_km": 500,
            "price_eur": 25000,
            "owner_type": "private",
            "make": "Renault",
            "model": "Clio",
        }
        result = self.filt.run(data)
        assert result.status == "warning"
        assert result.score == 0.65
        assert "quasi-neuf" in result.message
        assert "compteur" not in result.message.lower()
        assert result.details["is_recent_low_km"] is True

    def test_old_car_low_km_still_suspicious(self):
        """Vehicule de 10 ans avec tres peu de km → toujours suspect (compteur)."""
        data = {
            "year_model": "2016",
            "mileage_km": 5000,
            "price_eur": 8000,
            "make": "Peugeot",
            "model": "308",
        }
        result = self.filt.run(data)
        assert result.status == "warning"
        assert "bas pour l'année" in result.message
        assert result.details["is_recent_low_km"] is False

    def test_very_low_price_warns(self):
        data = {
            "year_model": "2020",
            "mileage_km": 60000,
            "price_eur": 200,
        }
        result = self.filt.run(data)
        assert result.status in ("warning", "fail")

    def test_voiture_sans_permis_aixam_low_annual_km_is_normal(self):
        """AIXAM (VSP) ne suit pas la moyenne 15 000 km/an d'une voiture classique."""
        data = {
            "make": "AIXAM",
            "model": "City",
            "year_model": "2022",
            "mileage_km": 24000,
            "power_fiscal_cv": 1,
            "price_eur": 9790,
        }
        result = self.filt.run(data)
        assert result.status == "pass"
        assert result.details["category"] == "voiture_sans_permis"
        assert result.details["is_voiture_sans_permis"] is True
        assert result.details["avg_km_per_year"] == 6000

    def test_sportive_low_km_is_positive(self):
        """Sportive >400cv DIN avec km faible : message positif, pas suspect."""
        data = {
            "make": "Ferrari",
            "model": "488",
            "year_model": "2018",
            "mileage_km": 12000,
            "price_eur": 95000,
            "power_din_hp": 670,
        }
        result = self.filt.run(data)
        assert result.status == "warning"
        assert result.score == 0.85
        assert "sportive" in result.message.lower()
        assert "plutôt bien" in result.message
        assert "compteur" not in result.message.lower()
        assert result.details["is_sportive"] is True
        assert result.details["category"] == "sportive"
        assert result.details["avg_km_per_year"] == 5000

    def test_sportive_fiscal_hp_low_km_positive(self):
        """Sportive >45cv fiscaux avec km faible : message positif."""
        data = {
            "make": "Porsche",
            "model": "911",
            "year_model": "2016",
            "mileage_km": 20000,
            "price_eur": 95000,
            "power_fiscal_cv": 48,
        }
        result = self.filt.run(data)
        assert result.details["is_sportive"] is True
        assert result.details["category"] == "sportive"
        assert "sportive" in result.message.lower()
        assert result.score == 0.85

    def test_sportive_normal_km_passes(self):
        """Sportive avec km normal pour son age : pass."""
        data = {
            "make": "Lamborghini",
            "model": "Huracan",
            "year_model": "2022",
            "mileage_km": 18000,
            "price_eur": 95000,
            "power_din_hp": 610,
        }
        result = self.filt.run(data)
        assert result.status == "pass"
        assert result.details["is_sportive"] is True

    def test_non_sportive_low_km_still_suspicious(self):
        """Voiture normale 150cv avec km faible : toujours suspect."""
        data = {
            "make": "Peugeot",
            "model": "308",
            "year_model": "2014",
            "mileage_km": 15000,
            "price_eur": 8000,
            "power_din_hp": 150,
        }
        result = self.filt.run(data)
        assert result.status == "warning"
        assert "bas pour l'année" in result.message
        assert result.details["is_sportive"] is False
