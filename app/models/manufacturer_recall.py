"""Modele ManufacturerRecall : rappels constructeur connus pour un vehicule."""

from datetime import datetime, timezone

from app.extensions import db


class ManufacturerRecall(db.Model):
    """Rappel constructeur officiel lie a un vehicule du catalogue."""

    __tablename__ = "manufacturer_recalls"
    __table_args__ = (
        db.UniqueConstraint(
            "vehicle_id",
            "recall_type",
            "year_start",
            "year_end",
            name="uq_recall_vehicle_type_years",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=False, index=True)
    recall_type = db.Column(db.String(60), nullable=False, index=True)
    year_start = db.Column(db.Integer, nullable=False)
    year_end = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text, nullable=False)
    gov_url = db.Column(db.String(300), nullable=True)
    severity = db.Column(db.String(20), nullable=False, default="critical")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    vehicle = db.relationship("Vehicle", backref="recalls")

    def __repr__(self) -> str:
        return f"<ManufacturerRecall {self.recall_type} vehicle_id={self.vehicle_id}>"
