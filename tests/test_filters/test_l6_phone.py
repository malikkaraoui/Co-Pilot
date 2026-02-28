"""Tests for L6 Phone Filter (multi-country)."""

from app.filters.l6_phone import L6PhoneFilter


class TestL6PhoneFilter:
    def setup_method(self):
        self.filt = L6PhoneFilter()

    # ── France (default) ─────────────────────────────────────────────

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

    def test_foreign_prefix_warns_in_france(self):
        result = self.filt.run({"phone": "+48612345678", "country": "FR"})
        assert result.status == "warning"
        assert result.details["is_foreign"] is True
        assert "+48" in result.message

    def test_german_prefix_warns_in_france(self):
        result = self.filt.run({"phone": "+49 171 1234567", "country": "FR"})
        assert result.status == "warning"
        assert "+49" in result.details["prefix"]

    def test_non_standard_format_still_passes(self):
        """Telephone present mais format non-standard : pass (le tel est la)."""
        result = self.filt.run({"phone": "123"})
        assert result.status == "pass"
        assert result.details["type"] == "present_unverified"

    # ── No phone: private vs pro ─────────────────────────────────────

    def test_no_phone_private_neutral_no_penalty(self):
        """Particulier sans telephone : neutral (exclu du scoring)."""
        result = self.filt.run({"owner_type": "private"})
        assert result.status == "neutral"
        assert "pénalité" in result.message

    def test_no_phone_empty_owner_neutral(self):
        """Owner type vide : considere comme particulier → neutral."""
        result = self.filt.run({})
        assert result.status == "neutral"

    def test_particulier_no_phone_returns_neutral(self):
        """owner_type francais 'particulier' → neutral."""
        result = self.filt.run({"owner_type": "particulier"})
        assert result.status == "neutral"

    def test_no_phone_pro_fails_zero(self):
        """Pro sans telephone : fail score 0.0."""
        result = self.filt.run({"owner_type": "pro"})
        assert result.status == "fail"
        assert result.score == 0.0
        assert "professionnel" in result.message

    def test_has_phone_lbc_skips(self):
        """LBC telephone cache derriere login."""
        result = self.filt.run({"has_phone": True})
        assert result.status == "skip"
        assert "LeBonCoin" in result.message

    # ── Suisse (.ch) ─────────────────────────────────────────────────

    def test_swiss_mobile_passes_on_ch(self):
        """Numero mobile suisse +41 79 sur .ch : pass."""
        result = self.filt.run({"phone": "+41 79 123 45 67", "country": "CH"})
        assert result.status == "pass"
        assert result.details["type"] == "mobile_ch"

    def test_swiss_landline_passes_on_ch(self):
        """Numero fixe suisse sur .ch : pass."""
        result = self.filt.run({"phone": "+41 22 345 67 89", "country": "CH"})
        assert result.status == "pass"
        assert result.details["type"] == "landline_ch"

    def test_swiss_number_not_foreign_on_ch(self):
        """Un +41 sur .ch ne doit PAS etre signale comme etranger."""
        result = self.filt.run({"phone": "+41791234567", "country": "CH"})
        assert result.status == "pass"
        assert result.details.get("is_foreign") is not True

    def test_swiss_number_flagged_as_foreign_on_fr(self):
        """Un +41 sur .fr EST etranger."""
        result = self.filt.run({"phone": "+41791234567", "country": "FR"})
        assert result.status == "warning"
        assert result.details["is_foreign"] is True

    def test_french_number_flagged_as_foreign_on_ch(self):
        """Un +33 sur .ch EST etranger."""
        result = self.filt.run({"phone": "+33612345678", "country": "CH"})
        assert result.status == "warning"
        assert result.details["is_foreign"] is True

    # ── Allemagne (.de) ──────────────────────────────────────────────

    def test_german_mobile_passes_on_de(self):
        """Numero mobile allemand sur .de : pass."""
        result = self.filt.run({"phone": "+49 151 12345678", "country": "DE"})
        assert result.status == "pass"
        assert result.details["type"] == "mobile_de"

    def test_german_number_not_foreign_on_de(self):
        """Un +49 sur .de ne doit PAS etre signale comme etranger."""
        result = self.filt.run({"phone": "+4915112345678", "country": "DE"})
        assert result.status == "pass"
        assert result.details.get("is_foreign") is not True

    # ── Generic countries ────────────────────────────────────────────

    def test_local_prefix_passes_on_it(self):
        """Un +39 sur .it : indicatif local."""
        result = self.filt.run({"phone": "+393401234567", "country": "IT"})
        assert result.status == "pass"

    def test_no_prefix_passes_generic(self):
        """Numero local sans indicatif : pass generique."""
        result = self.filt.run({"phone": "0612345678", "country": "IT"})
        assert result.status == "pass"

    # ── France-specific checks still work ────────────────────────────

    def test_telemarketing_prefix_fails(self):
        result = self.filt.run({"phone": "0162345678", "country": "FR"})
        assert result.status == "fail"
        assert "démarchage" in result.message

    def test_virtual_number_warns(self):
        result = self.filt.run({"phone": "0644661234", "country": "FR"})
        assert result.status == "warning"
        assert "virtuel" in result.message.lower()
