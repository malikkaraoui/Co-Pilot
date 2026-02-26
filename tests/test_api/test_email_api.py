"""Tests for /api/email-draft endpoint."""

from unittest.mock import MagicMock, patch

from app.models.scan import ScanLog


class TestEmailDraftAPI:
    def test_generate_draft_success(self, app, client, db):
        """POST /api/email-draft creates a draft and returns it."""
        with app.app_context():
            scan = ScanLog(
                url="https://example.com/voiture",
                raw_data={
                    "make": "Peugeot",
                    "model": "308",
                    "price": 15000,
                    "owner_type": "private",
                },
                score=70,
                vehicle_make="Peugeot",
                vehicle_model="308",
            )
            db.session.add(scan)
            db.session.commit()

            mock_draft = MagicMock()
            mock_draft.id = 1
            mock_draft.generated_text = "Bonjour..."
            mock_draft.status = "draft"
            mock_draft.vehicle_make = "Peugeot"
            mock_draft.vehicle_model = "308"
            mock_draft.tokens_used = 150

            with patch(
                "app.api.routes.email_service.generate_email_draft",
                return_value=mock_draft,
            ):
                resp = client.post("/api/email-draft", json={"scan_id": scan.id})

            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert data["data"]["generated_text"] == "Bonjour..."

    def test_returns_400_without_scan_id(self, app, client):
        """POST /api/email-draft without scan_id returns 400."""
        with app.app_context():
            resp = client.post("/api/email-draft", json={})
            assert resp.status_code == 400

    def test_returns_404_for_unknown_scan(self, app, client, db):
        """POST /api/email-draft with unknown scan_id returns 404."""
        with app.app_context():
            with patch(
                "app.api.routes.email_service.generate_email_draft",
                side_effect=ValueError("Scan introuvable: 99999"),
            ):
                resp = client.post("/api/email-draft", json={"scan_id": 99999})
            assert resp.status_code == 404

    def test_returns_503_when_gemini_down(self, app, client, db):
        """POST /api/email-draft returns 503 if Gemini unreachable."""
        with app.app_context():
            scan = ScanLog(
                url="https://example.com",
                raw_data={"make": "Renault", "model": "Clio"},
                score=50,
                vehicle_make="Renault",
                vehicle_model="Clio",
            )
            db.session.add(scan)
            db.session.commit()

            with patch(
                "app.api.routes.email_service.generate_email_draft",
                side_effect=ConnectionError("Gemini erreur"),
            ):
                resp = client.post("/api/email-draft", json={"scan_id": scan.id})
            assert resp.status_code == 503
