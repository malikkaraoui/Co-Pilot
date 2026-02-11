"""Tests for the Leboncoin extraction service."""

import pytest

from app.errors import ExtractionError
from app.services.extraction import extract_ad_data
from tests.mocks.mock_leboncoin import (
    EMPTY_NEXT_DATA,
    MALFORMED_NEXT_DATA,
    MINIMAL_AD_NEXT_DATA,
    VALID_AD_NEXT_DATA,
)


class TestExtractAdData:
    """Tests for extract_ad_data()."""

    def test_valid_ad_full_fields(self):
        result = extract_ad_data(VALID_AD_NEXT_DATA)
        assert result["make"] == "Peugeot"
        assert result["model"] == "3008"
        assert result["year_model"] == "2019"
        assert result["price_eur"] == 18500
        assert result["mileage_km"] == 75000
        assert result["fuel"] == "Diesel"
        assert result["gearbox"] == "Manuelle"
        assert result["doors"] == 5
        assert result["seats"] == 5
        assert result["color"] == "Gris"
        assert result["power_fiscal_cv"] == 7
        assert result["power_din_hp"] == 120
        assert result["phone"] == "0612345678"
        assert result["location"]["city"] == "Lyon"
        assert result["location"]["region"] == "Auvergne-Rhone-Alpes"

    def test_minimal_ad(self):
        result = extract_ad_data(MINIMAL_AD_NEXT_DATA)
        assert result["make"] == "Renault"
        assert result["model"] == "Clio"
        assert result["price_eur"] == 5000
        assert result["mileage_km"] is None
        assert result["phone"] is None

    def test_malformed_raises_extraction_error(self):
        with pytest.raises(ExtractionError, match="Could not locate ad payload"):
            extract_ad_data(MALFORMED_NEXT_DATA)

    def test_empty_raises_extraction_error(self):
        with pytest.raises(ExtractionError, match="Could not locate ad payload"):
            extract_ad_data(EMPTY_NEXT_DATA)

    def test_non_dict_raises_extraction_error(self):
        with pytest.raises(ExtractionError, match="must be a dict"):
            extract_ad_data("not a dict")

    def test_raw_attributes_preserved(self):
        result = extract_ad_data(VALID_AD_NEXT_DATA)
        assert "Marque" in result["raw_attributes"]
        assert result["raw_attributes"]["Marque"] == "Peugeot"
