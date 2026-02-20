"""Modeles Vehicle et VehicleSpec."""

from datetime import datetime, timezone

from app.extensions import db


class Vehicle(db.Model):
    """Vehicule connu dans la base de reference (70 modeles, objectif 200+)."""

    __tablename__ = "vehicles"
    __table_args__ = (db.UniqueConstraint("brand", "model", name="uq_vehicle_brand_model"),)

    id = db.Column(db.Integer, primary_key=True)
    brand = db.Column(db.String(80), nullable=False, index=True)
    model = db.Column(db.String(120), nullable=False, index=True)
    generation = db.Column(db.String(80))
    year_start = db.Column(db.Integer)
    year_end = db.Column(db.Integer)
    enrichment_status = db.Column(
        db.String(20), nullable=False, default="complete", server_default="complete"
    )
    # Override admin : seuil minimum d'annonces pour l'argus (NULL = dynamique auto)
    argus_min_samples = db.Column(db.Integer, nullable=True)
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
    body_type = db.Column(db.String(40))
    number_of_seats = db.Column(db.Integer)
    capacity_cm3 = db.Column(db.Integer)
    max_torque_nm = db.Column(db.Integer)
    curb_weight_kg = db.Column(db.Integer)
    length_mm = db.Column(db.Integer)
    width_mm = db.Column(db.Integer)
    height_mm = db.Column(db.Integer)
    mixed_consumption_l100km = db.Column(db.Float)
    co2_emissions_gkm = db.Column(db.Integer)
    acceleration_0_100s = db.Column(db.Float)
    max_speed_kmh = db.Column(db.Integer)
    reliability_rating = db.Column(db.Float)
    known_issues = db.Column(db.Text)
    expected_costs = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<VehicleSpec {self.vehicle_id} {self.fuel_type}>"
