"""Tests pour /api/scan-report."""

from unittest.mock import patch


class TestScanReportApi:
    def test_returns_pdf_when_generation_succeeds(self, app, client):
        """POST /api/scan-report retourne un PDF telechargeable."""
        with app.app_context():
            with patch(
                "app.services.report_service.generate_scan_report_pdf",
                return_value=b"%PDF-1.4\nmock\n",
            ):
                resp = client.post("/api/scan-report", json={"scan_id": 42})

        assert resp.status_code == 200
        assert resp.headers["Content-Type"].startswith("application/pdf")
        assert "okazcar-rapport-42.pdf" in resp.headers["Content-Disposition"]
        assert resp.data.startswith(b"%PDF-")

    def test_returns_400_without_scan_id(self, app, client):
        """POST /api/scan-report sans scan_id retourne 400."""
        with app.app_context():
            resp = client.post("/api/scan-report", json={})

        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False
        assert data["error"] == "VALIDATION_ERROR"

    def test_returns_404_for_unknown_scan(self, app, client):
        """POST /api/scan-report retourne 404 si le scan n'existe pas."""
        with app.app_context():
            with patch(
                "app.services.report_service.generate_scan_report_pdf",
                side_effect=ValueError("Scan introuvable: 99999"),
            ):
                resp = client.post("/api/scan-report", json={"scan_id": 99999})

        assert resp.status_code == 404
        data = resp.get_json()
        assert data["error"] == "NOT_FOUND"
