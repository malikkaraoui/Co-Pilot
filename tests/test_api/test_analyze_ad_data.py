"""Tests for POST /api/analyze with pre-normalized ad_data (multi-site support)."""

import pytest

from app import create_app
from app.extensions import db


@pytest.fixture()
def client():
    """Client isole -- le pipeline /api/analyze commit des Vehicle qui ne doivent
    pas fuiter dans les autres tests de la suite (ex. test_import_csv)."""
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.drop_all()


def _autoscout_ad_data():
    """Minimal AutoScout24 ad_data matching extract_ad_data() output."""
    return {
        "title": "AUDI Q5 Sportback 40 TDI",
        "price_eur": 43900,
        "currency": "CHF",
        "make": "AUDI",
        "model": "Q5",
        "year_model": "2023",
        "mileage_km": 29299,
        "fuel": "Diesel",
        "gearbox": "Automatique",
        "power_din_hp": 204,
        "image_count": 23,
        "owner_type": "pro",
        "description": "Fahrzeug mit Garantie",
        "location": {"city": "Niederlenz", "region": None},
        "publication_date": "2026-02-11T09:00:20.284Z",
        "has_phone": True,
        "phone": "+41628929454",
        "raw_attributes": {},
        "has_urgent": False,
        "has_highlight": False,
        "has_boost": False,
        "days_online": None,
        "index_date": None,
        "days_since_refresh": None,
        "republished": False,
        "lbc_estimation": None,
    }


class TestAnalyzeAdData:
    def test_ad_data_returns_score(self, client):
        resp = client.post(
            "/api/analyze",
            json={
                "url": "https://www.autoscout24.ch/fr/d/audi-q5-20201676",
                "ad_data": _autoscout_ad_data(),
                "source": "autoscout24",
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "score" in data["data"]
        assert 0 <= data["data"]["score"] <= 100
        assert len(data["data"]["filters"]) > 0

    def test_ad_data_source_stored(self, client):
        resp = client.post(
            "/api/analyze",
            json={
                "url": "https://www.autoscout24.ch/fr/d/audi-q5-20201676",
                "ad_data": _autoscout_ad_data(),
                "source": "autoscout24",
            },
        )
        assert resp.status_code == 200

    def test_legacy_next_data_still_works(self, client):
        resp = client.post(
            "/api/analyze",
            json={
                "url": "https://www.leboncoin.fr/ad/voitures/12345",
                "next_data": {
                    "props": {
                        "pageProps": {
                            "ad": {
                                "list_id": 12345,
                                "attributes": [
                                    {"key": "brand", "value": "Peugeot"},
                                    {"key": "model", "value": "208"},
                                    {"key": "regdate", "value": "2021"},
                                ],
                                "price": [15000],
                                "images": {"nb_images": 5},
                                "location": {"region_name": "Ile-de-France"},
                                "owner": {"type": "private"},
                            }
                        }
                    }
                },
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_neither_next_data_nor_ad_data_returns_400(self, client):
        resp = client.post("/api/analyze", json={"url": "https://example.com"})
        assert resp.status_code == 400

    def test_as24_url_with_missing_make_model_does_not_trigger_not_a_vehicle(self, client):
        """T4: AS24 URL + null make/model must NOT return NOT_A_VEHICLE.

        _extract_url_category only works for LBC URLs. For non-LBC sources,
        the NOT_A_VEHICLE check should be skipped.
        """
        ad_data = _autoscout_ad_data()
        ad_data["make"] = None
        ad_data["model"] = None
        resp = client.post(
            "/api/analyze",
            json={
                "url": "https://www.autoscout24.ch/fr/d/unknown-20201676",
                "ad_data": ad_data,
                "source": "autoscout24",
            },
        )
        data = resp.get_json()
        # Should NOT be NOT_A_VEHICLE (that detection is LBC-specific)
        assert data.get("error") != "NOT_A_VEHICLE"

    def test_as24_ad_data_with_partial_fields_returns_score(self, client):
        """T5: AS24 ad_data with minimal fields still returns a score."""
        resp = client.post(
            "/api/analyze",
            json={
                "url": "https://www.autoscout24.de/angebote/bmw-320-12345",
                "ad_data": {
                    "make": "BMW",
                    "model": "320",
                    "price_eur": 25000,
                    "year_model": "2021",
                },
                "source": "autoscout24",
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert 0 <= data["data"]["score"] <= 100

    def test_chf_price_converted_to_eur(self, client):
        """CHF price from AS24.ch should be converted to EUR for filters."""
        ad_data = _autoscout_ad_data()
        ad_data["price_eur"] = 43900
        ad_data["currency"] = "CHF"
        resp = client.post(
            "/api/analyze",
            json={
                "url": "https://www.autoscout24.ch/fr/d/audi-q5-20201676",
                "ad_data": ad_data,
                "source": "autoscout24",
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        vehicle = data["data"]["vehicle"]
        # The vehicle price should be the EUR-converted amount
        assert vehicle["price"] == round(43900 * 0.94)
        # Original price and currency should be preserved
        assert vehicle["price_original"] == 43900
        assert vehicle["currency"] == "CHF"

    def test_eur_price_not_converted(self, client):
        """EUR prices should pass through without conversion."""
        resp = client.post(
            "/api/analyze",
            json={
                "url": "https://www.autoscout24.de/angebote/bmw-320-12345",
                "ad_data": {
                    "make": "BMW",
                    "model": "320",
                    "price_eur": 25000,
                    "currency": "EUR",
                    "year_model": "2021",
                },
                "source": "autoscout24",
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        vehicle = data["data"]["vehicle"]
        # No conversion: price stays at 25000, no original/currency fields
        assert vehicle["price"] == 25000
        assert "price_original" not in vehicle
        assert "currency" not in vehicle

    def test_no_currency_field_not_converted(self, client):
        """LBC ads without currency field should not trigger conversion."""
        resp = client.post(
            "/api/analyze",
            json={
                "url": "https://www.leboncoin.fr/ad/voitures/12345",
                "next_data": {
                    "props": {
                        "pageProps": {
                            "ad": {
                                "list_id": 12345,
                                "attributes": [
                                    {"key": "brand", "value": "Peugeot"},
                                    {"key": "model", "value": "208"},
                                    {"key": "regdate", "value": "2021"},
                                ],
                                "price": [15000],
                                "images": {"nb_images": 5},
                                "location": {"region_name": "Ile-de-France"},
                                "owner": {"type": "private"},
                            }
                        }
                    }
                },
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        vehicle = data["data"]["vehicle"]
        assert vehicle["price"] == 15000
        assert "price_original" not in vehicle
