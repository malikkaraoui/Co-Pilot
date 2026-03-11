"""Modele EngineReliability : fiabilite connue d'une famille de moteur."""

from datetime import datetime, timezone

from app.extensions import db


class EngineReliability(db.Model):
    """Score de fiabilite d'une famille moteur, base sur agregation de sources."""

    __tablename__ = "engine_reliabilities"
    __table_args__ = (
        db.UniqueConstraint("engine_code", "brand", name="uq_engine_reliability_code_brand"),
    )

    id = db.Column(db.Integer, primary_key=True)
    engine_code = db.Column(db.String(80), nullable=False, index=True)
    brand = db.Column(db.String(60), nullable=False)
    fuel_type = db.Column(db.String(20), nullable=False, index=True)  # "Diesel" / "Essence"
    score = db.Column(db.Float, nullable=False)  # 0.0 – 5.0
    note = db.Column(db.Text, nullable=True)
    weaknesses = db.Column(db.Text, nullable=True)
    source_count = db.Column(db.Integer, default=0)
    # Patterns CSV pour matcher VehicleSpec.engine (substring search)
    # ex: "BlueHDi,HDi 130,DW10"
    match_patterns = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<EngineReliability {self.brand} {self.engine_code} {self.score}>"

    @property
    def stars(self) -> str:
        """Representation etoiles (ex: '★★★★☆')."""
        full = int(self.score)
        half = 1 if (self.score - full) >= 0.5 else 0
        empty = 5 - full - half
        return "★" * full + ("½" if half else "") + "☆" * empty

    def patterns_list(self) -> list[str]:
        """Retourne la liste des patterns de matching."""
        if not self.match_patterns:
            return [self.engine_code]
        return [p.strip() for p in self.match_patterns.split(",") if p.strip()]
