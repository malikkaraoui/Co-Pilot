"""Tests for ManufacturerRecall model."""

from app.models.manufacturer_recall import ManufacturerRecall


class TestManufacturerRecall:
    def test_repr(self):
        recall = ManufacturerRecall(
            vehicle_id=1,
            recall_type="takata_airbag",
            year_start=2005,
            year_end=2015,
            description="Airbag Takata defectueux",
            severity="critical",
        )
        assert "takata_airbag" in repr(recall)
        assert "vehicle_id=1" in repr(recall)
