"""Modele VehicleSynthesis -- synthese LLM d'un vehicule a partir de transcripts YouTube.

On utilise Gemini pour generer une synthese des avis/retours sur un vehicule
a partir des sous-titres YouTube collectes. Ca donne a l'acheteur un resume
des points forts/faibles du vehicule sans avoir a regarder 10 videos.
"""

from datetime import datetime, timezone

from app.extensions import db


class VehicleSynthesis(db.Model):
    """Synthese LLM generee a partir des sous-titres YouTube.

    Le vehicle_id est nullable car on peut generer une synthese avant
    d'avoir identifie le vehicule exact en base (matching flou en cours).
    Le status suit le cycle : draft -> published (ou rejected).
    On garde le prompt_used et les source_video_ids pour la tracabilite.
    """

    __tablename__ = "vehicle_syntheses"

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=True, index=True)
    make = db.Column(db.String(80), nullable=False)
    model = db.Column(db.String(80), nullable=False)
    year = db.Column(db.Integer, nullable=True)
    fuel = db.Column(db.String(30), nullable=True)

    llm_model = db.Column(db.String(80), nullable=False)
    prompt_used = db.Column(db.Text, nullable=False)
    # IDs des videos utilisees pour generer la synthese
    source_video_ids = db.Column(db.JSON, default=list)
    # Nombre total de caracteres de transcript envoyes au LLM
    raw_transcript_chars = db.Column(db.Integer, default=0)
    synthesis_text = db.Column(db.Text, nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="draft")

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    vehicle = db.relationship("Vehicle", backref="syntheses")

    def __repr__(self):
        return f"<VehicleSynthesis {self.make} {self.model} [{self.status}]>"
