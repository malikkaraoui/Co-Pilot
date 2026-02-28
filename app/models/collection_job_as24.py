"""Modele CollectionJobAS24 -- file d'attente de collecte prix pour AutoScout24."""

from datetime import datetime, timezone

from app.extensions import db


class CollectionJobAS24(db.Model):
    """Job de collecte de prix a executer par l'extension Chrome sur AutoScout24."""

    __tablename__ = "collection_jobs_as24"

    id = db.Column(db.Integer, primary_key=True)
    make = db.Column(db.String(80), nullable=False, index=True)
    model = db.Column(db.String(80), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False)
    region = db.Column(db.String(80), nullable=False)
    fuel = db.Column(db.String(30), nullable=True)
    gearbox = db.Column(db.String(20), nullable=True)
    hp_range = db.Column(db.String(20), nullable=True)
    country = db.Column(db.String(5), nullable=False, default="CH")
    tld = db.Column(db.String(5), nullable=False)  # ch, de, at, fr, it, es, be, nl, lu
    slug_make = db.Column(db.String(80), nullable=False)  # AS24 URL slug (ex: "vw")
    slug_model = db.Column(db.String(80), nullable=False)  # AS24 URL slug (ex: "tiguan")
    search_strategy = db.Column(
        db.String(20), nullable=False, default="zip_radius"
    )  # zip_radius, national, canton
    currency = db.Column(db.String(5), nullable=False, default="CHF")  # CHF, EUR
    source_url = db.Column(db.String(500), nullable=True)  # URL annonce AS24 source

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
            "tld",
            name="uq_collection_job_as24_key",
        ),
    )

    def __repr__(self):
        return (
            f"<CollectionJobAS24 {self.make} {self.model} {self.year} "
            f"{self.region} [{self.status}] tld={self.tld}>"
        )
