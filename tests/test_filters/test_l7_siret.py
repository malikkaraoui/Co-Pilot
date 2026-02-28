"""Tests for L7 SIRET/UID Filter (multi-country)."""

from unittest.mock import patch

from app.errors import ExternalAPIError
from app.filters.l7_siret import L7SiretFilter, _clean_uid, validate_uid_checksum


class TestL7SiretFilter:
    def setup_method(self):
        self.filt = L7SiretFilter(timeout=5)

    # ── France (default) ─────────────────────────────────────────────

    def test_no_siret_skips(self):
        result = self.filt.run({})
        assert result.status == "skip"

    def test_private_seller_neutral(self):
        """Particulier retourne neutral (exclu du scoring), pas skip."""
        result = self.filt.run({"owner_type": "private", "siret": "12345678901234"})
        assert result.status == "neutral"
        assert "particulier" in result.message.lower()

    def test_particulier_returns_neutral(self):
        """owner_type francais 'particulier' aussi."""
        result = self.filt.run({"owner_type": "particulier"})
        assert result.status == "neutral"

    def test_invalid_format_fails(self):
        result = self.filt.run({"siret": "ABC123"})
        assert result.status == "fail"
        assert "format" in result.message.lower()

    def test_too_short_fails(self):
        result = self.filt.run({"siret": "123"})
        assert result.status == "fail"

    def test_active_company_passes(self):
        api_response = {
            "etat_administratif": "A",
            "unite_legale": {"denomination": "Auto Malik SARL"},
        }
        with patch.object(self.filt, "_call_fr_api", return_value=api_response):
            result = self.filt.run({"siret": "12345678901234"})
        assert result.status == "pass"
        assert "active" in result.message.lower()

    def test_closed_company_warns(self):
        api_response = {
            "etat_administratif": "F",
            "unite_legale": {"denomination": "Ferme SARL"},
        }
        with patch.object(self.filt, "_call_fr_api", return_value=api_response):
            result = self.filt.run({"siret": "12345678901234"})
        assert result.status == "warning"

    def test_not_found_fails(self):
        with patch.object(self.filt, "_call_fr_api", return_value=None):
            result = self.filt.run({"siret": "12345678901234"})
        assert result.status == "fail"
        assert "introuvable" in result.message.lower()

    def test_api_error_skips(self):
        with patch.object(self.filt, "_call_fr_api", side_effect=ExternalAPIError("timeout")):
            result = self.filt.run({"siret": "12345678901234"})
        assert result.status == "skip"
        assert "indisponible" in result.message.lower()

    # ── Pro sans identifiant (multi-pays) ────────────────────────────

    def test_pro_no_siret_france_warns(self):
        result = self.filt.run({"owner_type": "pro", "country": "FR"})
        assert result.status == "warning"
        assert "SIRET" in result.message

    def test_pro_no_uid_ch_warns(self):
        result = self.filt.run({"owner_type": "pro", "country": "CH"})
        assert result.status == "warning"
        assert "UID" in result.message

    def test_pro_no_id_other_warns(self):
        result = self.filt.run({"owner_type": "pro", "country": "DE"})
        assert result.status == "warning"
        assert "entreprise" in result.message

    # ── Plateforme verifiee (AS24) ──────────────────────────────────

    def test_pro_no_siret_as24_ch_passes_1(self):
        """Pro sur AS24 : plateforme verifie le statut pro = pass 1.0."""
        result = self.filt.run(
            {
                "owner_type": "pro",
                "country": "CH",
                "source": "autoscout24",
            }
        )
        assert result.status == "pass"
        assert result.score == 1.0
        assert "vérifié" in result.message
        assert result.details["platform_verified"] is True

    def test_pro_no_siret_as24_with_rating(self):
        """Pro sur AS24 avec note : pass 1.0, note dans le message."""
        result = self.filt.run(
            {
                "owner_type": "pro",
                "country": "CH",
                "source": "autoscout24",
                "dealer_rating": 4.8,
                "dealer_review_count": 350,
            }
        )
        assert result.status == "pass"
        assert result.score == 1.0
        assert "4.8" in result.message
        assert "350" in result.message

    def test_pro_no_siret_as24_de(self):
        """Pro sur AS24.de : meme logique, pass 1.0."""
        result = self.filt.run(
            {
                "owner_type": "pro",
                "country": "DE",
                "source": "autoscout24",
            }
        )
        assert result.status == "pass"
        assert result.score == 1.0

    # ── Dealer rating compense (hors plateforme verifiee) ─────────

    def test_pro_no_siret_with_high_rating_passes(self):
        """Pro sans SIRET (hors AS24) avec excellente note vendeur : pass."""
        result = self.filt.run(
            {
                "owner_type": "pro",
                "country": "CH",
                "dealer_rating": 4.8,
                "dealer_review_count": 350,
            }
        )
        assert result.status == "pass"
        assert result.score == 0.7
        assert "4.8" in result.message
        assert "350" in result.message

    def test_pro_no_siret_with_low_rating_still_warns(self):
        """Pro sans SIRET avec note mediocre : warning normal."""
        result = self.filt.run(
            {
                "owner_type": "pro",
                "country": "FR",
                "dealer_rating": 3.2,
                "dealer_review_count": 5,
            }
        )
        assert result.status == "warning"
        assert "SIRET" in result.message

    def test_pro_no_siret_with_few_reviews_still_warns(self):
        """Pro sans SIRET avec bonne note mais trop peu d'avis : warning."""
        result = self.filt.run(
            {
                "owner_type": "pro",
                "country": "DE",
                "dealer_rating": 4.9,
                "dealer_review_count": 3,
            }
        )
        assert result.status == "warning"
        assert "entreprise" in result.message

    def test_pro_no_siret_with_exact_threshold_passes(self):
        """Pro sans SIRET avec note = 4.0 et 20 avis : juste au seuil, pass."""
        result = self.filt.run(
            {
                "owner_type": "pro",
                "country": "FR",
                "dealer_rating": 4.0,
                "dealer_review_count": 20,
            }
        )
        assert result.status == "pass"
        assert result.score == 0.7

    # ── Suisse : UID ─────────────────────────────────────────────────

    def test_valid_uid_format_passes(self):
        """UID valide avec checksum correct : pass (sans Zefix)."""
        # CHE-116.281.710 est un UID reel (Swisscom)
        result = self.filt.run({"siret": "CHE-116.281.710", "country": "CH"})
        assert result.status == "pass"
        assert "UID valide" in result.message
        assert result.details["formatted"] == "CHE-116.281.710"

    def test_invalid_uid_format_fails(self):
        """UID avec format invalide."""
        result = self.filt.run({"siret": "XY-123", "country": "CH"})
        assert result.status == "fail"
        assert "format" in result.message.lower()

    def test_uid_bad_checksum_fails(self):
        """UID avec chiffre de controle incorrect."""
        result = self.filt.run({"siret": "CHE-123.456.789", "country": "CH"})
        assert result.status == "fail"
        assert "contrôle" in result.message

    def test_uid_zefix_active(self):
        """UID avec Zefix retournant une entreprise active."""
        zefix_response = {"name": "Swiss Auto AG", "status": "active"}
        with (
            patch.dict("os.environ", {"ZEFIX_USER": "test", "ZEFIX_PASSWORD": "pass"}),
            patch.object(self.filt, "_call_zefix_api", return_value=zefix_response),
        ):
            result = self.filt.run({"siret": "CHE-116.281.710", "country": "CH"})
        assert result.status == "pass"
        assert result.score == 0.9
        assert "Swiss Auto AG" in result.message

    def test_uid_zefix_not_found(self):
        """UID valide mais introuvable dans Zefix."""
        with (
            patch.dict("os.environ", {"ZEFIX_USER": "test", "ZEFIX_PASSWORD": "pass"}),
            patch.object(self.filt, "_call_zefix_api", return_value=None),
        ):
            result = self.filt.run({"siret": "CHE-116.281.710", "country": "CH"})
        assert result.status == "fail"
        assert "introuvable" in result.message.lower()

    def test_uid_zefix_api_error_fallback(self):
        """Zefix indisponible : fallback sur validation format seule."""
        with (
            patch.dict("os.environ", {"ZEFIX_USER": "test", "ZEFIX_PASSWORD": "pass"}),
            patch.object(self.filt, "_call_zefix_api", side_effect=ExternalAPIError("timeout")),
        ):
            result = self.filt.run({"siret": "CHE-116.281.710", "country": "CH"})
        assert result.status == "pass"
        assert result.score == 0.7
        assert "indisponible" in result.message.lower()


class TestUidValidation:
    """Tests unitaires pour les fonctions de validation UID."""

    def test_clean_uid_standard_format(self):
        assert _clean_uid("CHE-116.281.710") == "116281710"

    def test_clean_uid_no_separators(self):
        assert _clean_uid("CHE116281710") == "116281710"

    def test_clean_uid_dots(self):
        assert _clean_uid("CHE.116.281.710") == "116281710"

    def test_clean_uid_invalid(self):
        assert _clean_uid("XY123") is None

    def test_clean_uid_too_short(self):
        assert _clean_uid("CHE-12.34") is None

    def test_checksum_valid(self):
        """CHE-116.281.710 (Swisscom) : checksum valide."""
        assert validate_uid_checksum("116281710") is True

    def test_checksum_invalid(self):
        """Chiffre de controle modifie : invalide."""
        assert validate_uid_checksum("116281711") is False

    def test_checksum_too_short(self):
        assert validate_uid_checksum("12345") is False

    def test_checksum_non_digit(self):
        assert validate_uid_checksum("ABCDEFGHI") is False
