"""Tests for L11 Recall Filter."""

from unittest.mock import patch

from app.filters.l11_recall import L11RecallFilter


class TestL11RecallFilter:
    def setup_method(self):
        self.filt = L11RecallFilter()

    @patch("app.filters.l11_recall._find_recalls")
    def test_vehicle_with_recall_fails(self, mock_find):
        """Vehicule concerne par Takata → fail score 0.0."""
        mock_find.return_value = [
            {
                "recall_type": "takata_airbag",
                "description": "Airbag Takata defectueux",
                "gov_url": "https://www.ecologie.gouv.fr/rappel-airbag-takata",
                "severity": "critical",
            }
        ]
        result = self.filt.run({"make": "BMW", "model": "Serie 3", "year": 2010})
        assert result.status == "fail"
        assert result.score == 0.0
        assert "Takata" in result.message or "rappel" in result.message.lower()
        assert result.details["gov_url"] == "https://www.ecologie.gouv.fr/rappel-airbag-takata"

    @patch("app.filters.l11_recall._find_recalls")
    def test_vehicle_without_recall_passes(self, mock_find):
        """Vehicule non concerne → pass score 1.0."""
        mock_find.return_value = []
        result = self.filt.run({"make": "Dacia", "model": "Sandero", "year": 2022})
        assert result.status == "pass"
        assert result.score == 1.0

    def test_missing_year_neutral(self):
        """Annee manquante → neutral."""
        result = self.filt.run({"make": "BMW", "model": "Serie 3"})
        assert result.status == "neutral"

    def test_missing_make_neutral(self):
        """Marque manquante → neutral."""
        result = self.filt.run({"year": 2010})
        assert result.status == "neutral"
