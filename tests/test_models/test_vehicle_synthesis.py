"""Tests for VehicleSynthesis model."""

from app.extensions import db
from app.models.vehicle_synthesis import VehicleSynthesis


class TestVehicleSynthesisModel:
    def test_create_synthesis(self, app):
        """Create a VehicleSynthesis record with all fields."""
        with app.app_context():
            s = VehicleSynthesis(
                make="Peugeot",
                model="308",
                year=2019,
                fuel="diesel",
                llm_model="mistral",
                prompt_used="test prompt",
                source_video_ids=[1, 2, 3],
                raw_transcript_chars=5000,
                synthesis_text="Points forts: confort",
                status="draft",
            )
            db.session.add(s)
            db.session.commit()

            found = db.session.get(VehicleSynthesis, s.id)
            assert found is not None
            assert found.make == "Peugeot"
            assert found.status == "draft"
            assert found.source_video_ids == [1, 2, 3]

    def test_default_status_is_draft(self, app):
        """Default status is draft."""
        with app.app_context():
            s = VehicleSynthesis(
                make="Renault",
                model="Clio",
                llm_model="mistral",
                prompt_used="test",
                synthesis_text="test",
            )
            db.session.add(s)
            db.session.commit()
            assert s.status == "draft"
