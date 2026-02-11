"""Tests for L6 Phone Filter."""

from app.filters.l6_phone import L6PhoneFilter


class TestL6PhoneFilter:
    def setup_method(self):
        self.filt = L6PhoneFilter()

    def test_french_mobile_passes(self):
        result = self.filt.run({"phone": "06 12 34 56 78"})
        assert result.status == "pass"
        assert result.details["type"] == "mobile_fr"

    def test_french_mobile_07_passes(self):
        result = self.filt.run({"phone": "0712345678"})
        assert result.status == "pass"

    def test_french_mobile_with_prefix_passes(self):
        result = self.filt.run({"phone": "+33612345678"})
        assert result.status == "pass"

    def test_french_landline_passes(self):
        result = self.filt.run({"phone": "01 23 45 67 89"})
        assert result.status == "pass"
        assert result.details["type"] == "landline_fr"

    def test_foreign_prefix_warns(self):
        result = self.filt.run({"phone": "+48612345678"})
        assert result.status == "warning"
        assert result.details["is_foreign"] is True
        assert "+48" in result.message

    def test_german_prefix_warns(self):
        result = self.filt.run({"phone": "+49 171 1234567"})
        assert result.status == "warning"
        assert "+49" in result.details["prefix"]

    def test_no_phone_skips(self):
        result = self.filt.run({})
        assert result.status == "skip"

    def test_suspect_format(self):
        result = self.filt.run({"phone": "123"})
        assert result.status == "warning"
        assert result.details["type"] == "unknown"
