"""Tests for L7 SIRET Filter."""

from unittest.mock import patch

from app.errors import ExternalAPIError
from app.filters.l7_siret import L7SiretFilter


class TestL7SiretFilter:
    def setup_method(self):
        self.filt = L7SiretFilter(timeout=5)

    def test_no_siret_skips(self):
        result = self.filt.run({})
        assert result.status == "skip"

    def test_invalid_format_fails(self):
        result = self.filt.run({"siret": "ABC123"})
        assert result.status == "fail"
        assert "format" in result.message.lower()

    def test_too_short_fails(self):
        result = self.filt.run({"siret": "123"})
        assert result.status == "fail"

    def test_active_company_passes(self):
        api_response = {
            "etat_administratif": "A",
            "unite_legale": {"denomination": "Auto Malik SARL"},
        }
        with patch.object(self.filt, "_call_api", return_value=api_response):
            result = self.filt.run({"siret": "12345678901234"})
        assert result.status == "pass"
        assert "active" in result.message.lower()

    def test_closed_company_warns(self):
        api_response = {
            "etat_administratif": "F",
            "unite_legale": {"denomination": "Ferme SARL"},
        }
        with patch.object(self.filt, "_call_api", return_value=api_response):
            result = self.filt.run({"siret": "12345678901234"})
        assert result.status == "warning"

    def test_not_found_fails(self):
        with patch.object(self.filt, "_call_api", return_value=None):
            result = self.filt.run({"siret": "12345678901234"})
        assert result.status == "fail"
        assert "introuvable" in result.message.lower()

    def test_api_error_skips(self):
        with patch.object(self.filt, "_call_api", side_effect=ExternalAPIError("timeout")):
            result = self.filt.run({"siret": "12345678901234"})
        assert result.status == "skip"
        assert "indisponible" in result.message.lower()
