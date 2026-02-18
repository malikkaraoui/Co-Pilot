"""Tests for L2 Referentiel Filter."""

from unittest.mock import patch

from app.filters.l2_referentiel import L2ReferentielFilter
from app.models.vehicle import Vehicle
from app.services.vehicle_lookup import is_generic_model


class TestL2ReferentielFilter:
    def setup_method(self):
        self.filt = L2ReferentielFilter()

    def test_model_found(self):
        mock_vehicle = Vehicle(id=1, brand="Peugeot", model="3008", generation="II")
        with patch("app.services.vehicle_lookup.find_vehicle", return_value=mock_vehicle):
            result = self.filt.run({"make": "Peugeot", "model": "3008"})
        assert result.status == "pass"
        assert result.score == 1.0
        assert result.details["vehicle_id"] == 1

    def test_model_not_found(self):
        with patch("app.services.vehicle_lookup.find_vehicle", return_value=None):
            result = self.filt.run({"make": "MG", "model": "ZS EV"})
        assert result.status == "warning"
        assert "ne connaît pas" in result.message

    def test_missing_make_skips(self):
        result = self.filt.run({"model": "3008"})
        assert result.status == "skip"

    def test_missing_model_skips(self):
        result = self.filt.run({"make": "Peugeot"})
        assert result.status == "skip"

    def test_model_not_found_uses_brand_key(self):
        """Unrecognized details should use 'brand' not 'make' key."""
        with patch("app.services.vehicle_lookup.find_vehicle", return_value=None):
            result = self.filt.run({"make": "Tesla", "model": "Model 3"})
        assert "brand" in result.details
        assert result.details["brand"] == "Tesla"
        assert "make" not in result.details

    def test_generic_model_autres_skips(self):
        """LBC 'Autres' = modele non precise → skip (pas warning)."""
        result = self.filt.run({"make": "Honda", "model": "Autres"})
        assert result.status == "skip"
        assert "non précisé" in result.message

    def test_generic_model_autre_skips(self):
        """Variante sans 's' : 'Autre' → skip."""
        result = self.filt.run({"make": "Mini", "model": "Autre"})
        assert result.status == "skip"

    def test_generic_model_case_insensitive(self):
        """Detection generique insensible a la casse."""
        result = self.filt.run({"make": "BMW", "model": "AUTRES"})
        assert result.status == "skip"


class TestIsGenericModel:
    """Tests unitaires pour is_generic_model()."""

    def test_autres(self):
        assert is_generic_model("Autres") is True

    def test_autre(self):
        assert is_generic_model("Autre") is True

    def test_other(self):
        assert is_generic_model("Other") is True

    def test_uppercase(self):
        assert is_generic_model("AUTRES") is True

    def test_real_model(self):
        assert is_generic_model("3008") is False

    def test_real_model_with_spaces(self):
        assert is_generic_model("Classe A") is False
