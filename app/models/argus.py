"""Modele ArgusPrice -- donnees de reference de prix geolocalisees."""

from datetime import datetime, timezone

from app.extensions import db


class ArgusPrice(db.Model):
    """Reference de prix argus, geolocalisee par region."""

    __tablename__ = "argus_prices"

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=False)
    region = db.Column(db.String(80), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    mileage_bracket = db.Column(db.String(40))
    price_low = db.Column(db.Integer)
    price_mid = db.Column(db.Integer)
    price_high = db.Column(db.Integer)
    source = db.Column(db.String(80))
    collected_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    vehicle = db.relationship("Vehicle", backref="argus_prices")

    def __repr__(self):
        return f"<ArgusPrice {self.vehicle_id} {self.region} {self.year}>"
