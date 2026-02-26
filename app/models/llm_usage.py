"""Modele LLMUsage -- suivi des couts et tokens LLM."""

from datetime import datetime, timezone

from app.extensions import db


class LLMUsage(db.Model):
    """Enregistrement de chaque appel LLM pour suivi des couts."""

    __tablename__ = "llm_usages"

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.String(100), nullable=False, index=True)
    provider = db.Column(db.String(30), nullable=False)
    model = db.Column(db.String(80), nullable=False)
    feature = db.Column(db.String(50), nullable=False)
    prompt_tokens = db.Column(db.Integer, nullable=False, default=0)
    completion_tokens = db.Column(db.Integer, nullable=False, default=0)
    total_tokens = db.Column(db.Integer, nullable=False, default=0)
    estimated_cost_eur = db.Column(db.Float, nullable=False, default=0.0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<LLMUsage {self.provider}/{self.feature} {self.total_tokens}tok>"
