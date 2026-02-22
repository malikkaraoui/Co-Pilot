"""Tests for L4 LBC estimation fallback (tier 3)."""

from app.filters.l4_price import L4PriceFilter


class TestL4LbcEstimation:
    def test_uses_lbc_estimation_when_no_market_or_argus(self, app):
        """L4 should use LBC estimation as last-resort fallback."""
        with app.app_context():
            f = L4PriceFilter()
            data = {
                "price_eur": 14900,
                "make": "Jeep",
                "model": "Renegade",
                "year_model": "2020",
                "location": {"region": "Nouvelle-Aquitaine"},
                "fuel": "hybride rechargeable",
                "lbc_estimation": {"low": 17320, "high": 19140},
            }
            result = f.run(data)
            # Should NOT be skip -- should use LBC estimation
            assert result.status != "skip"
            assert "estimation_lbc" in result.details.get("source", "")

    def test_lbc_estimation_message_mentions_estimation(self, app):
        """L4 with LBC estimation should mention it in the message."""
        with app.app_context():
            f = L4PriceFilter()
            data = {
                "price_eur": 14900,
                "make": "Jeep",
                "model": "Renegade",
                "year_model": "2020",
                "location": {"region": "Nouvelle-Aquitaine"},
                "fuel": "hybride rechargeable",
                "lbc_estimation": {"low": 17320, "high": 19140},
            }
            result = f.run(data)
            assert "estimation" in result.message.lower() or "lbc" in result.message.lower()

    def test_lbc_estimation_reduced_scoring(self, app):
        """LBC estimation should apply reduced delta (halved)."""
        with app.app_context():
            f = L4PriceFilter()
            # Prix 18230 (milieu fourchette), annonce 14900 → delta brut = -18.2%
            # Avec reduction x0.5 → delta effectif = -9.1% → pass (<=10%)
            data = {
                "price_eur": 14900,
                "make": "Jeep",
                "model": "Renegade",
                "year_model": "2020",
                "location": {"region": "Nouvelle-Aquitaine"},
                "fuel": "hybride rechargeable",
                "lbc_estimation": {"low": 17320, "high": 19140},
            }
            result = f.run(data)
            # With reduced scoring, -18% becomes -9% → should be pass
            assert result.status == "pass"
            assert result.details.get("lbc_estimation_low") == 17320
            assert result.details.get("lbc_estimation_high") == 19140

    def test_lbc_estimation_not_used_when_market_exists(self, app):
        """L4 should prefer MarketPrice over LBC estimation."""
        with app.app_context():
            from datetime import datetime, timedelta, timezone

            from app.extensions import db
            from app.models.market_price import MarketPrice

            # Insert MarketPrice directly to avoid auto_create_vehicle side effects
            now = datetime.now(timezone.utc)
            mp = MarketPrice(
                make="Lancia",
                model="Ypsilon",
                year=2021,
                region="Bretagne",
                price_min=12000,
                price_median=14000,
                price_mean=14000,
                price_max=16000,
                price_std=1414.0,
                price_iqr_mean=14000,
                price_p25=13000,
                price_p75=15000,
                sample_count=5,
                collected_at=now,
                refresh_after=now + timedelta(hours=24),
            )
            db.session.add(mp)
            db.session.commit()

            f = L4PriceFilter()
            data = {
                "price_eur": 14000,
                "make": "Lancia",
                "model": "Ypsilon",
                "year_model": "2021",
                "location": {"region": "Bretagne"},
                "lbc_estimation": {"low": 10000, "high": 12000},
            }
            result = f.run(data)
            # Should use market data, not LBC estimation
            assert result.details.get("source") == "marche_leboncoin"

    def test_lbc_estimation_ignored_when_invalid(self, app):
        """L4 should skip if LBC estimation is malformed."""
        with app.app_context():
            f = L4PriceFilter()
            data = {
                "price_eur": 14900,
                "make": "Jeep",
                "model": "Renegade",
                "year_model": "2020",
                "location": {"region": "Nouvelle-Aquitaine"},
                "lbc_estimation": {"low": None, "high": None},
            }
            result = f.run(data)
            assert result.status == "skip"
