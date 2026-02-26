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
            "price_eur": 15000,
            "year_model": "2019",
            "mileage_km": 85000,
            "fuel": "Diesel",
            "owner_type": "private",
            "owner_name": "Jean",
            "days_online": 25,
            "url": "https://example.com",
        }
        filters = [
            {
                "filter_id": "L4",
                "status": "warning",
                "message": "Prix 10% sous argus",
                "details": {"deviation_pct": -10},
            },
        ]
        prompt = build_email_prompt(scan_data, filters)
        assert "Peugeot" in prompt
        assert "308" in prompt
        assert "15000" in prompt

    def test_includes_filter_signals(self):
        """Prompt mentions warning/fail filter signals with details."""
        scan_data = {
            "make": "Renault",
            "model": "Clio",
            "price_eur": 8000,
            "owner_type": "pro",
            "days_online": 45,
            "url": "https://example.com",
        }
        filters = [
            {
                "filter_id": "L4",
                "status": "fail",
                "message": "Prix tres bas",
                "details": {"reference_price": 12000},
            },
            {
                "filter_id": "L8",
                "status": "warning",
                "message": "Signaux import",
                "details": {"signals": ["plaque etrangere"]},
            },
        ]
        prompt = build_email_prompt(scan_data, filters)
        assert "ALERTE" in prompt
        assert "ATTENTION" in prompt
        assert "import" in prompt.lower()

    def test_adapts_to_seller_type(self):
        """Prompt adapts language for pro vs private sellers."""
        base = {
            "make": "BMW",
            "model": "Serie 3",
            "price_eur": 25000,
            "url": "https://example.com",
            "days_online": 10,
        }
        pro_prompt = build_email_prompt({**base, "owner_type": "pro"}, [])
        private_prompt = build_email_prompt({**base, "owner_type": "private"}, [])
        assert "PROFESSIONNEL" in pro_prompt
        assert "PARTICULIER" in private_prompt

    def test_includes_few_shot_example(self):
        """Prompt includes a few-shot email example."""
        scan_data = {"make": "Audi", "model": "A3", "url": "https://example.com"}
        prompt = build_email_prompt(scan_data, [])
        assert "EXEMPLE DE BON EMAIL" in prompt

    def test_includes_extra_fields(self):
        """Prompt includes gearbox, color, image_count, location."""
        scan_data = {
            "make": "Toyota",
            "model": "Yaris",
            "gearbox": "Manuelle",
            "color": "Blanc",
            "image_count": 3,
            "location": {"city": "Lyon"},
            "url": "https://example.com",
        }
        prompt = build_email_prompt(scan_data, [])
        assert "Manuelle" in prompt
        assert "Blanc" in prompt
        assert "Lyon" in prompt
        assert "3" in prompt


class TestGenerateEmailDraft:
    def test_creates_draft_from_scan(self, app, db):
        """generate_email_draft creates an EmailDraft with token count."""
        with app.app_context():
            scan = ScanLog(
                url="https://www.leboncoin.fr/voitures/12345.htm",
                raw_data={},
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
                details={"deviation_pct": -10},
            )
            db.session.add(fr)
            db.session.commit()

            with (
                patch(
                    "app.services.email_service.extract_ad_data",
                    return_value={
                        "make": "Peugeot",
                        "model": "308",
                        "price_eur": 15000,
                        "year_model": "2019",
                        "mileage_km": 85000,
                        "fuel": "Diesel",
                        "owner_type": "private",
                        "owner_name": "Jean",
                    },
                ),
                patch(
                    "app.services.email_service.gemini_service.generate_text",
                    return_value=(
                        "Bonjour Jean, je suis interesse par votre 308...",
                        250,
                    ),
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
            assert draft.tokens_used == 250

    def test_raises_on_unknown_scan(self, app, db):
        """generate_email_draft raises ValueError for non-existent scan."""
        with app.app_context():
            with pytest.raises(ValueError, match="Scan introuvable"):
                generate_email_draft(99999)
