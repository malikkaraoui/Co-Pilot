"""Tests for L10 Listing Age Filter."""

from unittest.mock import patch

from app.filters.l10_listing_age import L10ListingAgeFilter, _threshold_for_price


class TestThresholdForPrice:
    """Tests unitaires pour _threshold_for_price."""

    def test_cheap_vehicle(self):
        assert _threshold_for_price(8_000) == 21

    def test_mid_range(self):
        assert _threshold_for_price(15_000) == 35

    def test_high_end(self):
        assert _threshold_for_price(35_000) == 50

    def test_premium(self):
        assert _threshold_for_price(60_000) == 75

    def test_none_fallback(self):
        assert _threshold_for_price(None) == 35

    def test_boundary_10k(self):
        """10 000 EUR pile tombe dans la tranche 10k-25k."""
        assert _threshold_for_price(10_000) == 35

    def test_boundary_25k(self):
        assert _threshold_for_price(25_000) == 50


class TestL10ListingAgeFilter:
    def setup_method(self):
        self.filt = L10ListingAgeFilter()

    @patch("app.filters.l10_listing_age._get_market_median_days", return_value=None)
    def test_fresh_listing_passes(self, _mock):
        """Annonce de 2 jours a 15k → pass score 1.0."""
        result = self.filt.run({"days_online": 2, "price_eur": 15_000})
        assert result.status == "pass"
        assert result.score == 1.0
        assert "récente" in result.message

    @patch("app.filters.l10_listing_age._get_market_median_days", return_value=None)
    def test_normal_duration_passes(self, _mock):
        """Annonce de 20 jours a 15k (seuil 35j) → pass score 0.8."""
        result = self.filt.run({"days_online": 20, "price_eur": 15_000})
        assert result.status == "pass"
        assert result.score == 0.8
        assert result.details["threshold_days"] == 35

    @patch("app.filters.l10_listing_age._get_market_median_days", return_value=None)
    def test_above_threshold_warns(self, _mock):
        """Annonce de 30 jours a 8k (seuil 21j, ratio 1.43) → warning 0.5."""
        result = self.filt.run({"days_online": 30, "price_eur": 8_000})
        assert result.status == "warning"
        assert result.score == 0.5
        assert result.details["threshold_days"] == 21

    @patch("app.filters.l10_listing_age._get_market_median_days", return_value=None)
    def test_very_stagnant_warns(self, _mock):
        """Annonce de 90 jours a 8k (seuil 21j, ratio 4.3) → warning 0.3."""
        result = self.filt.run({"days_online": 90, "price_eur": 8_000})
        assert result.status == "warning"
        assert result.score == 0.3
        assert "stagnante" in result.message

    @patch("app.filters.l10_listing_age._get_market_median_days", return_value=None)
    def test_stagnant_republished_fails(self, _mock):
        """Annonce stagnante + republied → fail 0.2."""
        result = self.filt.run(
            {
                "days_online": 90,
                "price_eur": 8_000,
                "republished": True,
            }
        )
        assert result.status == "fail"
        assert result.score == 0.2
        assert "republié" in result.message

    def test_days_online_missing_skips(self):
        """Pas de days_online → skip."""
        result = self.filt.run({"price_eur": 15_000})
        assert result.status == "skip"

    @patch("app.filters.l10_listing_age._get_market_median_days", return_value=None)
    def test_republished_normal_duration_mentions(self, _mock):
        """Republied mais duree normale → pass avec mention."""
        result = self.filt.run(
            {
                "days_online": 5,
                "price_eur": 15_000,
                "republished": True,
            }
        )
        assert result.status == "pass"
        assert "(republié)" in result.message

    @patch("app.filters.l10_listing_age._get_market_median_days", return_value=None)
    def test_premium_higher_tolerance(self, _mock):
        """Vehicule a 60k : 50 jours est normal (seuil 75j)."""
        result = self.filt.run({"days_online": 50, "price_eur": 60_000})
        assert result.status == "pass"
        assert result.score == 0.8
        assert result.details["threshold_days"] == 75

    @patch("app.filters.l10_listing_age._get_market_median_days", return_value=20)
    def test_market_median_used_when_available(self, _mock):
        """Mediane marche 20j dispo → utilise comme seuil."""
        result = self.filt.run(
            {
                "days_online": 30,
                "price_eur": 15_000,
                "make": "Peugeot",
                "model": "208",
            }
        )
        assert result.status == "warning"
        assert result.details["threshold_source"] == "marche"
        assert result.details["threshold_days"] == 20
        assert result.details["market_median_days"] == 20

    @patch("app.filters.l10_listing_age._get_market_median_days", return_value=None)
    def test_no_market_data_falls_back_to_price(self, _mock):
        """Pas assez de scans → fallback seuils par prix."""
        result = self.filt.run(
            {
                "days_online": 10,
                "price_eur": 8_000,
                "make": "Dacia",
                "model": "Sandero",
            }
        )
        assert result.details["threshold_source"] == "prix"
        assert "market_median_days" not in result.details

    @patch("app.filters.l10_listing_age._get_market_median_days", return_value=None)
    def test_details_contain_ratio(self, _mock):
        """Les details contiennent le ratio calcule."""
        result = self.filt.run({"days_online": 42, "price_eur": 21_000})
        assert "ratio" in result.details
        assert result.details["ratio"] == round(42 / 35, 2)

    @patch("app.filters.l10_listing_age._get_market_median_days", return_value=None)
    def test_republished_above_threshold_reduces_score(self, _mock):
        """Republied + au-dessus du seuil (mais <2x) → score reduit."""
        result = self.filt.run(
            {
                "days_online": 40,
                "price_eur": 8_000,
                "republished": True,
            }
        )
        assert result.status == "warning"
        assert result.score == 0.4  # 0.5 - 0.1
        assert "republié" in result.message
