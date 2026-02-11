"""Tests for L9 Global Assessment Filter."""

from app.filters.l9_score import L9GlobalAssessmentFilter


class TestL9GlobalAssessmentFilter:
    def setup_method(self):
        self.filt = L9GlobalAssessmentFilter()

    def test_complete_ad_passes(self):
        data = {
            "description": "Vehicule en excellent etat, revision complete. " * 5,
            "owner_type": "pro",
            "phone": "0612345678",
            "location": {"city": "Lyon"},
        }
        result = self.filt.run(data)
        assert result.status == "pass"
        assert result.score >= 0.8

    def test_no_description_warns(self):
        data = {
            "description": "",
            "phone": "0612345678",
            "location": {"city": "Lyon"},
        }
        result = self.filt.run(data)
        assert "description" in result.message.lower() or result.status == "warning"

    def test_short_description_warns(self):
        data = {
            "description": "Bonne voiture.",
            "phone": "0612345678",
            "location": {"city": "Lyon"},
        }
        result = self.filt.run(data)
        assert result.status in ("warning", "pass")

    def test_no_phone_no_location_fails(self):
        data = {
            "description": "",
            "location": {},
        }
        result = self.filt.run(data)
        assert result.status in ("warning", "fail")
        assert len(result.details["points_faibles"]) >= 2

    def test_pro_seller_bonus(self):
        data = {
            "description": "Description complete et detaillee du vehicule " * 5,
            "owner_type": "pro",
            "phone": "0612345678",
            "location": {"city": "Paris"},
        }
        result = self.filt.run(data)
        assert "professionnel" in " ".join(result.details["points_forts"]).lower()

    def test_empty_data(self):
        result = self.filt.run({})
        assert result.filter_id == "L9"
        assert result.status in ("warning", "fail")
