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
        assert result["phone"] is None  # LBC cache le tel derriere une API
        assert result["has_phone"] is True  # has_phone vient du __NEXT_DATA__
        assert result["image_count"] == 8  # images = dict avec nb_images
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

    def test_publication_date_extracted(self):
        result = extract_ad_data(VALID_AD_NEXT_DATA)
        assert result["publication_date"] == "2026-01-10 14:30:00"
        assert isinstance(result["days_online"], int)
        assert result["days_online"] >= 0
        # Meme date first_pub et index → pas republished
        assert result["republished"] is False

    def test_publication_date_missing(self):
        result = extract_ad_data(MINIMAL_AD_NEXT_DATA)
        assert result["publication_date"] is None
        assert result["days_online"] is None
        assert result["republished"] is False

    def test_republished_detection(self):
        """Annonce avec first_publication et index_date differents = republished."""
        data = {
            "props": {
                "pageProps": {
                    "ad": {
                        "list_id": 123,
                        "subject": "Test",
                        "price": 10000,
                        "first_publication_date": "2025-06-01 10:00:00",
                        "index_date": "2026-02-14 04:30:00",
                        "attributes": [
                            {"key": "Marque", "value": "Peugeot"},
                            {"key": "Modèle", "value": "208"},
                        ],
                    }
                }
            }
        }
        result = extract_ad_data(data)
        assert result["republished"] is True
        assert result["days_online"] > 200  # depuis juin 2025

    def test_raw_attributes_preserved(self):
        result = extract_ad_data(VALID_AD_NEXT_DATA)
        assert "Marque" in result["raw_attributes"]
        assert result["raw_attributes"]["Marque"] == "Peugeot"
