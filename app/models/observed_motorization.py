"""Motorisations observees par combinaison (fuel + transmission + puissance).

Chaque ligne represente une combinaison unique de specs vue sur des annonces.
Quand une combinaison atteint le seuil de sources distinctes, elle est promue
automatiquement en VehicleSpec confirmee.
"""

from datetime import datetime, timezone

from app.extensions import db


class ObservedMotorization(db.Model):
    """Combinaison de specs observee sur les annonces du marche.

    Chaque ligne = une combinaison unique (fuel, transmission, power_din_hp)
    pour un vehicule, avec le nombre total d'occurrences et le nombre d'annonces
    distinctes (via source_ids). La promotion en VehicleSpec se declenche quand
    distinct_sources >= PROMOTION_THRESHOLD.
    """

    __tablename__ = "observed_motorizations"
    __table_args__ = (
        db.UniqueConstraint(
            "vehicle_id",
            "fuel",
            "transmission",
            "power_din_hp",
            name="uq_observed_moto_combo",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=False, index=True)
    fuel = db.Column(db.String(40), nullable=False)  # "essence", "diesel", "hybride"
    transmission = db.Column(db.String(40), nullable=False)  # "manuelle", "automatique"
    power_din_hp = db.Column(db.Integer, nullable=False)  # 130, 150, 204
    seats = db.Column(db.Integer, nullable=True)  # 5, 7 (optionnel)
    power_fiscal_cv = db.Column(db.Integer, nullable=True)  # puissance fiscale (LBC only)
    count = db.Column(db.Integer, nullable=False, default=1)
    distinct_sources = db.Column(db.Integer, nullable=False, default=1)
    source_ids = db.Column(db.Text, nullable=True)  # JSON array de hashes pour dedup
    promoted = db.Column(db.Boolean, nullable=False, default=False)
    promoted_at = db.Column(db.DateTime, nullable=True)
    last_seen_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    vehicle = db.relationship(
        "Vehicle", backref=db.backref("observed_motorizations", lazy="select")
    )

    def __repr__(self):
        return (
            f"<ObservedMotorization {self.fuel}/{self.transmission}/{self.power_din_hp}ch "
            f"x{self.count} promoted={self.promoted}>"
        )
