"""Modeles GeminiConfig et GeminiPromptConfig -- parametrage LLM Google."""

from datetime import datetime, timezone

from app.extensions import db


class GeminiConfig(db.Model):
    """Configuration singleton pour l'API Gemini."""

    __tablename__ = "gemini_config"

    id = db.Column(db.Integer, primary_key=True)
    api_key_encrypted = db.Column(db.String(500), nullable=False)
    model_name = db.Column(db.String(80), nullable=False, default="gemini-2.5-flash")
    max_daily_requests = db.Column(db.Integer, nullable=False, default=500)
    max_daily_cost_eur = db.Column(db.Float, nullable=False, default=1.0)
    is_active = db.Column(db.Boolean, nullable=False, default=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        status = "ON" if self.is_active else "OFF"
        return f"<GeminiConfig {self.model_name} [{status}]>"


class GeminiPromptConfig(db.Model):
    """Template de prompt configurable pour Gemini."""

    __tablename__ = "gemini_prompt_configs"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    system_prompt = db.Column(db.Text, nullable=False)
    task_prompt_template = db.Column(db.Text, nullable=False)
    max_output_tokens = db.Column(db.Integer, nullable=False, default=500)
    temperature = db.Column(db.Float, nullable=False, default=0.3)
    top_p = db.Column(db.Float, nullable=True, default=0.9)
    response_format_hint = db.Column(db.String(50), default="email_text")
    hallucination_guard = db.Column(db.Text, default="")
    max_sentences = db.Column(db.Integer, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<GeminiPromptConfig {self.name} v{self.version}>"
