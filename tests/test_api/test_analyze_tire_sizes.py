"""Tests de l'enrichissement `tire_sizes` dans POST /api/analyze."""

import json

from tests.mocks.mock_leboncoin import VALID_AD_NEXT_DATA


def test_analyze_includes_tire_sizes_when_available(client, monkeypatch, db):
    from app.services import tire_service

    def _fake_get_tire_sizes(make, model, year):  # noqa: ANN001
        return {
            "dimensions": [
                {"size": "205/55R16", "load_index": 91, "speed_index": "V", "is_stock": True},
            ],
            "source": "allopneus",
            "source_url": "https://example.com",
            "generation": "golf-vii",
            "year_range": "2012-2021",
        }

    monkeypatch.setattr(tire_service, "get_tire_sizes", _fake_get_tire_sizes)

    resp = client.post(
        "/api/analyze",
        data=json.dumps({"next_data": VALID_AD_NEXT_DATA}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    data = body["data"]
    assert "tire_sizes" in data
    assert data["tire_sizes"] is not None
    assert data["tire_sizes"]["dimensions"][0]["size"] == "205/55R16"


def test_analyze_swallows_tire_sizes_errors(client, monkeypatch, db):
    from app.services import tire_service

    def _boom(*_args, **_kwargs):
        raise ValueError("boom")

    monkeypatch.setattr(tire_service, "get_tire_sizes", _boom)

    resp = client.post(
        "/api/analyze",
        data=json.dumps({"next_data": VALID_AD_NEXT_DATA}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["data"].get("tire_sizes") is None
