"""Modele TireSize : dimensions de pneus par vehicule/generation."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.extensions import db


class TireSize(db.Model):
    """Dimensions de pneus par vehicule/generation, multi-source."""

    __tablename__ = "tire_sizes"

    id = db.Column(db.Integer, primary_key=True)

    # Identification vehicule (normalise lowercase)
    make = db.Column(db.String(80), nullable=False, index=True)  # "volkswagen"
    model = db.Column(db.String(120), nullable=False, index=True)  # "golf"
    # Ex: "Golf VII" (Allopneus) ou "Mk7 (5G)" (Wheel-Size)
    generation = db.Column(db.String(120), nullable=True)
    year_start = db.Column(db.Integer, nullable=True)
    year_end = db.Column(db.Integer, nullable=True)

    # Dimensions (JSON) — liste dedup de toutes les dimensions possibles
    # Format : [{"size": "205/55R16", "load_index": 91, "speed_index": "V", "is_stock": true}, ...]
    dimensions = db.Column(db.Text, nullable=False)  # JSON serialise

    # Metadonnees
    source = db.Column(db.String(30), nullable=False)  # "allopneus" | "wheel-size"
    source_url = db.Column(db.String(500), nullable=True)
    dimension_count = db.Column(db.Integer, default=0)
    collected_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Compteur de demandes (combien de scans ont demande ce vehicule)
    request_count = db.Column(db.Integer, default=0)

    __table_args__ = (
        db.UniqueConstraint("make", "model", "generation", name="uq_tire_make_model_gen"),
    )

    def get_dimensions_list(self) -> list[dict]:
        """Retourne les dimensions comme liste Python."""
        if not self.dimensions:
            return []
        try:
            return json.loads(self.dimensions)
        except json.JSONDecodeError:
            return []

    def set_dimensions_list(self, dims: list[dict]) -> None:
        """Serialise et stocke les dimensions."""
        self.dimensions = json.dumps(dims or [], ensure_ascii=False)
        self.dimension_count = len(dims or [])

    def __repr__(self) -> str:
        gen = f" {self.generation}" if self.generation else ""
        return f"<TireSize {self.make} {self.model}{gen} ({self.source})>"
