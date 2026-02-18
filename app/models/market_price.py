"""Modele MarketPrice -- cache des prix du marche collectes par crowdsourcing."""

import json
from datetime import datetime, timezone

from app.extensions import db


class MarketPrice(db.Model):
    """Prix du marche collectes depuis les annonces LeBonCoin par les utilisateurs de l'extension."""

    __tablename__ = "market_prices"

    id = db.Column(db.Integer, primary_key=True)
    make = db.Column(db.String(80), nullable=False, index=True)
    model = db.Column(db.String(80), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False)
    region = db.Column(db.String(80), nullable=False)
    fuel = db.Column(db.String(30), nullable=True)  # essence, diesel, electrique, hybride

    price_min = db.Column(db.Integer)
    price_median = db.Column(db.Integer)
    price_mean = db.Column(db.Integer)
    price_max = db.Column(db.Integer)
    price_std = db.Column(db.Float)
    sample_count = db.Column(db.Integer, default=0)

    # Details du calcul (JSON) pour transparence dans le dashboard
    # Format: {"raw_prices": [...], "kept_prices": [...], "excluded_prices": [...],
    #          "iqr_low": N, "iqr_high": N, "method": "iqr"}
    calculation_details = db.Column(db.Text, nullable=True)

    collected_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    refresh_after = db.Column(db.DateTime, nullable=False)

    __table_args__ = (
        db.UniqueConstraint(
            "make",
            "model",
            "year",
            "region",
            "fuel",
            name="uq_market_price_vehicle_region_fuel",
        ),
    )

    def get_calculation_details(self) -> dict | None:
        """Retourne les details du calcul en dict, ou None."""
        if not self.calculation_details:
            return None
        return json.loads(self.calculation_details)

    def __repr__(self):
        return f"<MarketPrice {self.make} {self.model} {self.year} {self.region}>"
