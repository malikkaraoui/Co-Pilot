"""Modele MarketPrice -- cache des prix du marche collectes par crowdsourcing."""

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

    price_min = db.Column(db.Integer)
    price_median = db.Column(db.Integer)
    price_mean = db.Column(db.Integer)
    price_max = db.Column(db.Integer)
    price_std = db.Column(db.Float)
    sample_count = db.Column(db.Integer, default=0)

    collected_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    refresh_after = db.Column(db.DateTime, nullable=False)

    __table_args__ = (
        db.UniqueConstraint(
            "make", "model", "year", "region", name="uq_market_price_vehicle_region"
        ),
    )

    def __repr__(self):
        return f"<MarketPrice {self.make} {self.model} {self.year} {self.region}>"
