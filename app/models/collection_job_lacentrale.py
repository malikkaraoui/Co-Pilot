"""Modele CollectionJobLacentrale -- file d'attente de collecte prix pour La Centrale."""

from datetime import datetime, timezone

from app.extensions import db


class CollectionJobLacentrale(db.Model):
    """Job de collecte de prix a executer par l'extension Chrome sur La Centrale."""

    __tablename__ = "collection_jobs_lacentrale"

    id = db.Column(db.Integer, primary_key=True)
    make = db.Column(db.String(80), nullable=False, index=True)
    model = db.Column(db.String(80), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False)
    region = db.Column(db.String(80), nullable=False)
    fuel = db.Column(db.String(30), nullable=True)
    gearbox = db.Column(db.String(20), nullable=True)
    hp_range = db.Column(db.String(20), nullable=True)
    country = db.Column(db.String(5), nullable=False, default="FR")

    priority = db.Column(db.Integer, nullable=False, default=1, index=True)
    status = db.Column(
        db.String(20), nullable=False, default="pending", index=True
    )  # pending, assigned, done, failed
    source_vehicle = db.Column(db.String(200), nullable=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    assigned_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.UniqueConstraint(
            "make",
            "model",
            "year",
            "region",
            "fuel",
            "gearbox",
            "hp_range",
            "country",
            name="uq_collection_job_lacentrale_key",
        ),
    )

    def __repr__(self):
        return (
            f"<CollectionJobLacentrale {self.make} {self.model} {self.year} "
            f"{self.region} [{self.status}]>"
        )
