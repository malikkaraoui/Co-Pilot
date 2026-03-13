"""Specs observees sur le marche pour un vehicule (motorisations, boites, puissances).

Complementaire a ObservedMotorization mais plus granulaire : ici on stocke
chaque valeur individuellement (ex: fuel="diesel", gearbox="automatique",
hp="150"). Ca sert a construire les filtres intelligents dans les jobs
de collecte : on sait quelles valeurs existent pour chaque vehicule
et on les utilise pour affiner les recherches.
"""

from datetime import datetime, timezone

from app.extensions import db


class VehicleObservedSpec(db.Model):
    """Spec observee lors de la collecte de prix marche.

    Chaque ligne = une valeur vue pour un type de spec (fuel, gearbox, hp)
    avec le nombre d'occurrences. Enrichi automatiquement a chaque collecte.

    Le count permet de distinguer les specs courantes (diesel 150ch = 200 occurrences)
    des specs rares (hybride 204ch = 3 occurrences) pour ponderer les jobs de collecte.
    """

    __tablename__ = "vehicle_observed_specs"
    __table_args__ = (
        db.UniqueConstraint(
            "vehicle_id",
            "spec_type",
            "spec_value",
            name="uq_observed_spec_vehicle_type_value",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=False, index=True)
    spec_type = db.Column(db.String(30), nullable=False)  # "fuel", "gearbox", "horse_power"
    spec_value = db.Column(db.String(80), nullable=False)
    count = db.Column(db.Integer, nullable=False, default=1)
    last_seen_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    vehicle = db.relationship("Vehicle", backref=db.backref("observed_specs", lazy="select"))

    def __repr__(self):
        return f"<VehicleObservedSpec {self.spec_type}={self.spec_value} x{self.count}>"
