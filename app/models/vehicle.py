"""Modeles Vehicle et VehicleSpec."""

from datetime import datetime, timezone

from app.extensions import db


class Vehicle(db.Model):
    """Vehicule connu dans la base de reference (20 modeles MVP)."""

    __tablename__ = "vehicles"

    id = db.Column(db.Integer, primary_key=True)
    brand = db.Column(db.String(80), nullable=False, index=True)
    model = db.Column(db.String(120), nullable=False, index=True)
    generation = db.Column(db.String(80))
    year_start = db.Column(db.Integer)
    year_end = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    specs = db.relationship("VehicleSpec", backref="vehicle", lazy="select")

    def __repr__(self):
        return f"<Vehicle {self.brand} {self.model}>"


class VehicleSpec(db.Model):
    """Specifications techniques et informations de fiabilite pour un vehicule."""

    __tablename__ = "vehicle_specs"

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=False)
    fuel_type = db.Column(db.String(40))
    transmission = db.Column(db.String(40))
    engine = db.Column(db.String(80))
    power_hp = db.Column(db.Integer)
    reliability_rating = db.Column(db.Float)
    known_issues = db.Column(db.Text)
    expected_costs = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<VehicleSpec {self.vehicle_id} {self.fuel_type}>"
