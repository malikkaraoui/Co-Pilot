"""Tests for email_service (seller email generation)."""

from unittest.mock import patch

import pytest

from app.models.filter_result import FilterResultDB
from app.models.scan import ScanLog
from app.services.email_service import build_email_prompt, generate_email_draft


class TestBuildEmailPrompt:
    def test_includes_vehicle_info(self):
        """Prompt includes vehicle make, model, price."""
        scan_data = {
            "make": "Peugeot",
            "model": "308",
            "price": 15000,
            "year": 2019,
            "mileage_km": 85000,
            "fuel": "Diesel",
            "owner_type": "private",
            "owner_name": "Jean",
            "days_online": 25,
            "url": "https://example.com",
        }
        filters = [
            {"filter_id": "L4", "status": "warning", "message": "Prix 10% sous argus"},
        ]
        prompt = build_email_prompt(scan_data, filters)
        assert "Peugeot" in prompt
        assert "308" in prompt
        assert "15000" in prompt or "15 000" in prompt

    def test_includes_filter_signals(self):
        """Prompt mentions warning/fail filter signals."""
        scan_data = {
            "make": "Renault",
            "model": "Clio",
            "price": 8000,
            "owner_type": "pro",
            "days_online": 45,
            "url": "https://example.com",
        }
        filters = [
            {"filter_id": "L4", "status": "fail", "message": "Prix tres bas"},
            {"filter_id": "L8", "status": "warning", "message": "Signaux import"},
        ]
        prompt = build_email_prompt(scan_data, filters)
        assert "L4" in prompt or "prix" in prompt.lower()
        assert "L8" in prompt or "import" in prompt.lower()

    def test_adapts_to_seller_type(self):
        """Prompt adapts language for pro vs private sellers."""
        base = {
            "make": "BMW",
            "model": "Serie 3",
            "price": 25000,
            "url": "https://example.com",
            "days_online": 10,
        }
        pro_prompt = build_email_prompt({**base, "owner_type": "pro"}, [])
        private_prompt = build_email_prompt({**base, "owner_type": "private"}, [])
        assert pro_prompt != private_prompt


class TestGenerateEmailDraft:
    def test_creates_draft_from_scan(self, app, db):
        """generate_email_draft creates an EmailDraft from a ScanLog."""
        with app.app_context():
            scan = ScanLog(
                url="https://www.leboncoin.fr/voitures/12345.htm",
                raw_data={
                    "make": "Peugeot",
                    "model": "308",
                    "price": 15000,
                    "year": 2019,
                    "mileage_km": 85000,
                    "fuel": "Diesel",
                    "owner_type": "private",
                    "owner_name": "Jean",
                    "days_online": 25,
                },
                score=65,
                vehicle_make="Peugeot",
                vehicle_model="308",
                price_eur=15000,
                days_online=25,
            )
            db.session.add(scan)
            db.session.commit()
            scan_id = scan.id

            fr = FilterResultDB(
                scan_id=scan_id,
                filter_id="L4",
                status="warning",
                score=0.5,
                message="Prix 10% sous argus",
            )
            db.session.add(fr)
            db.session.commit()

            with (
                patch(
                    "app.services.email_service.gemini_service.generate_text",
                    return_value="Bonjour Jean, je suis interesse par votre 308...",
                ),
                patch(
                    "app.services.email_service.gemini_service._get_model",
                    return_value="gemini-2.5-flash",
                ),
            ):
                draft = generate_email_draft(scan_id)

            assert draft.scan_id == scan_id
            assert draft.vehicle_make == "Peugeot"
            assert draft.vehicle_model == "308"
            assert draft.seller_type == "private"
            assert draft.status == "draft"
            assert "308" in draft.generated_text

    def test_raises_on_unknown_scan(self, app, db):
        """generate_email_draft raises ValueError for non-existent scan."""
        with app.app_context():
            with pytest.raises(ValueError, match="Scan introuvable"):
                generate_email_draft(99999)
