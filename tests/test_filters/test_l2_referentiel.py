"""Tests for L2 Referentiel Filter."""

from unittest.mock import patch

from app.filters.l2_referentiel import L2ReferentielFilter
from app.models.vehicle import Vehicle


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
        assert "ne connait pas" in result.message

    def test_missing_make_skips(self):
        result = self.filt.run({"model": "3008"})
        assert result.status == "skip"

    def test_missing_model_skips(self):
        result = self.filt.run({"make": "Peugeot"})
        assert result.status == "skip"
