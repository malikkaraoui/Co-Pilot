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

    def test_dual_model_attributes_uses_machine_key(self):
        """LBC envoie parfois deux attributs avec le meme key_label 'Modele'.

        Ex: Audi A6 Allroad → key="model" donne "A6" (modele de base),
        mais un second attribut avec key_label="Modele" donne "A6 Allroad".
        L'extraction doit preferer la cle machine ("model") pour rester
        coherente avec l'extension Chrome.
        """
        data = {
            "props": {
                "pageProps": {
                    "ad": {
                        "list_id": 999,
                        "subject": "Audi A6 allroad quattro",
                        "price": 25000,
                        "attributes": [
                            {
                                "key": "brand",
                                "key_label": "Marque",
                                "value": "AUDI",
                                "value_label": "Audi",
                            },
                            {
                                "key": "model",
                                "key_label": "Modèle",
                                "value": "A6",
                                "value_label": "A6",
                            },
                            {
                                "key": "vehicle_model_variant",
                                "key_label": "Modèle",
                                "value": "A6_ALLROAD",
                                "value_label": "A6 Allroad",
                            },
                            {
                                "key": "regdate",
                                "key_label": "Année modèle",
                                "value": "2015",
                                "value_label": "2015",
                            },
                        ],
                    }
                }
            }
        }
        result = extract_ad_data(data)
        assert result["make"] == "Audi"
        assert result["model"] == "A6", (
            "model doit etre 'A6' (cle machine), pas 'A6 Allroad' (key_label ecrase)"
        )

    def test_key_label_first_wins_no_overwrite(self):
        """Quand deux attributs partagent le meme key_label, le premier gagne."""
        data = {
            "props": {
                "pageProps": {
                    "ad": {
                        "list_id": 888,
                        "subject": "Test",
                        "price": 10000,
                        "attributes": [
                            {
                                "key": "brand",
                                "key_label": "Marque",
                                "value_label": "Audi",
                            },
                            {
                                "key": "model",
                                "key_label": "Modèle",
                                "value_label": "A6",
                            },
                            {
                                "key": "variant",
                                "key_label": "Modèle",
                                "value_label": "A6 Allroad",
                            },
                        ],
                    }
                }
            }
        }
        result = extract_ad_data(data)
        # raw_attributes stocke la cle machine pour chaque attribut
        assert result["raw_attributes"]["model"] == "A6"
        assert result["raw_attributes"]["variant"] == "A6 Allroad"
        # Mais le key_label "Modele" doit garder la premiere valeur (first-wins)
        assert result["raw_attributes"]["Modèle"] == "A6"

    def test_region_old_name_normalized_to_post_2016(self):
        """LBC envoie parfois les anciens noms de regions (pre-reforme 2016)."""
        data = {
            "props": {
                "pageProps": {
                    "ad": {
                        "list_id": 777,
                        "subject": "BMW Serie 3",
                        "price": 15990,
                        "location": {"region_name": "Aquitaine", "city": "Pau"},
                        "attributes": [
                            {"key": "brand", "value_label": "Bmw"},
                            {"key": "model", "value_label": "Serie 3"},
                        ],
                    }
                }
            }
        }
        result = extract_ad_data(data)
        assert result["location"]["region"] == "Nouvelle-Aquitaine"

    def test_region_post_2016_unchanged(self):
        """Les noms post-2016 ne sont pas modifies."""
        result = extract_ad_data(VALID_AD_NEXT_DATA)
        assert result["location"]["region"] == "Auvergne-Rhone-Alpes"

    @pytest.mark.parametrize(
        "old_region,expected",
        [
            ("Alsace", "Grand Est"),
            ("Lorraine", "Grand Est"),
            ("Nord-Pas-de-Calais", "Hauts-de-France"),
            ("Picardie", "Hauts-de-France"),
            ("Languedoc-Roussillon", "Occitanie"),
            ("Midi-Pyrenees", "Occitanie"),
            ("Haute-Normandie", "Normandie"),
            ("Basse-Normandie", "Normandie"),
            ("Bourgogne", "Bourgogne-Franche-Comte"),
            ("Limousin", "Nouvelle-Aquitaine"),
            ("Auvergne", "Auvergne-Rhone-Alpes"),
        ],
    )
    def test_region_old_names_all_mapped(self, old_region, expected):
        """Toutes les anciennes regions sont mappees vers les nouvelles."""
        from app.services.extraction import normalize_region

        assert normalize_region(old_region) == expected
