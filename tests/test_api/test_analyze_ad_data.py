"""Tests for POST /api/analyze with pre-normalized ad_data (multi-site support)."""

import pytest

from app import create_app
from app.extensions import db


@pytest.fixture()
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.app_context():
        db.create_all()
        yield app.test_client()


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
