"""Modele VehicleSynthesis -- synthese LLM d'un vehicule a partir de transcripts YouTube."""

from datetime import datetime, timezone

from app.extensions import db


class VehicleSynthesis(db.Model):
    """Synthese LLM generee a partir des sous-titres YouTube."""

    __tablename__ = "vehicle_syntheses"

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=True, index=True)
    make = db.Column(db.String(80), nullable=False)
    model = db.Column(db.String(80), nullable=False)
    year = db.Column(db.Integer, nullable=True)
    fuel = db.Column(db.String(30), nullable=True)

    llm_model = db.Column(db.String(80), nullable=False)
    prompt_used = db.Column(db.Text, nullable=False)
    source_video_ids = db.Column(db.JSON, default=list)
    raw_transcript_chars = db.Column(db.Integer, default=0)
    synthesis_text = db.Column(db.Text, nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="draft")

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    vehicle = db.relationship("Vehicle", backref="syntheses")

    def __repr__(self):
        return f"<VehicleSynthesis {self.make} {self.model} [{self.status}]>"
