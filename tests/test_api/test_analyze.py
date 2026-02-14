"""Tests for POST /api/analyze endpoint."""

import json

from tests.mocks.mock_leboncoin import (
    MALFORMED_NEXT_DATA,
    NON_VEHICLE_AD_NEXT_DATA,
    VALID_AD_NEXT_DATA,
    VEHICLE_IN_WRONG_CATEGORY_NEXT_DATA,
)


class TestAnalyzeEndpoint:
    def test_valid_ad_returns_score(self, client):
        resp = client.post(
            "/api/analyze",
            data=json.dumps({"next_data": VALID_AD_NEXT_DATA}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        data = body["data"]
        assert "score" in data
        assert 0 <= data["score"] <= 100
        assert "filters" in data
        assert data["vehicle"]["make"] == "Peugeot"
        assert data["vehicle"]["model"] == "3008"

    def test_no_json_body_returns_400(self, client):
        resp = client.post("/api/analyze", data="not json")
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["success"] is False
        assert body["error"] == "VALIDATION_ERROR"

    def test_missing_next_data_returns_400(self, client):
        resp = client.post(
            "/api/analyze",
            data=json.dumps({"url": "https://example.com"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["success"] is False
        assert body["error"] == "VALIDATION_ERROR"

    def test_malformed_next_data_returns_422(self, client):
        resp = client.post(
            "/api/analyze",
            data=json.dumps({"next_data": MALFORMED_NEXT_DATA}),
            content_type="application/json",
        )
        assert resp.status_code == 422
        body = resp.get_json()
        assert body["success"] is False
        assert body["error"] == "EXTRACTION_ERROR"

    def test_nine_filters_registered(self, client):
        """Les 9 filtres L1-L9 tournent sur une annonce valide."""
        resp = client.post(
            "/api/analyze",
            data=json.dumps({"next_data": VALID_AD_NEXT_DATA}),
            content_type="application/json",
        )
        body = resp.get_json()
        data = body["data"]
        filter_ids = [f["filter_id"] for f in data["filters"]]
        assert len(filter_ids) == 9
        for lid in ["L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9"]:
            assert lid in filter_ids

    def test_degradation_gracieuse_partial_score(self, client):
        """Quand des filtres skip, le score est partiel mais la reponse reste valide."""
        resp = client.post(
            "/api/analyze",
            data=json.dumps({"next_data": VALID_AD_NEXT_DATA}),
            content_type="application/json",
        )
        body = resp.get_json()
        data = body["data"]
        # Certains filtres devraient etre en "skip" (pas d'argus, pas de referentiel en base)
        statuses = [f["status"] for f in data["filters"]]
        assert "skip" in statuses  # L2, L4, L5 skip sans donnees en base
        assert data["is_partial"] is True


class TestNotAVehicleDetection:
    """Tests de la detection d'annonces non-vehicule."""

    def test_tires_ad_returns_not_a_vehicle(self, client):
        """Annonce de pneus dans equipement_auto → 422 NOT_A_VEHICLE."""
        resp = client.post(
            "/api/analyze",
            data=json.dumps(
                {
                    "url": "https://www.leboncoin.fr/ad/equipement_auto/3144651429",
                    "next_data": NON_VEHICLE_AD_NEXT_DATA,
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 422
        body = resp.get_json()
        assert body["success"] is False
        assert body["error"] == "NOT_A_VEHICLE"
        assert "bagnole" in body["message"].lower()
        assert body["data"]["category"] == "equipement_auto"

    def test_car_in_wrong_category_analyzed_normally(self, client):
        """Voiture dans equipement_auto (avec marque/modele) → analysee normalement."""
        resp = client.post(
            "/api/analyze",
            data=json.dumps(
                {
                    "url": "https://www.leboncoin.fr/ad/equipement_auto/3144609125",
                    "next_data": VEHICLE_IN_WRONG_CATEGORY_NEXT_DATA,
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["data"]["vehicle"]["make"] == "Renault"

    def test_normal_car_ad_analyzed(self, client):
        """Annonce voiture classique dans /voitures/ → analysee normalement."""
        resp = client.post(
            "/api/analyze",
            data=json.dumps(
                {
                    "url": "https://www.leboncoin.fr/ad/voitures/3089201001",
                    "next_data": VALID_AD_NEXT_DATA,
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True

    def test_no_url_with_car_data_analyzed(self, client):
        """Pas d'URL mais donnees vehicule presentes → analysee (backward compat)."""
        resp = client.post(
            "/api/analyze",
            data=json.dumps({"next_data": VALID_AD_NEXT_DATA}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
