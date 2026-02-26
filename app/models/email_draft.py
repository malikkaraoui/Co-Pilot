"""Modele EmailDraft -- brouillons d'emails vendeur generes par LLM."""

from datetime import datetime, timezone

from app.extensions import db


class EmailDraft(db.Model):
    """Brouillon d'email genere pour un vendeur a partir d'une analyse."""

    __tablename__ = "email_drafts"

    id = db.Column(db.Integer, primary_key=True)
    scan_id = db.Column(db.Integer, db.ForeignKey("scan_logs.id"), nullable=False, index=True)
    listing_url = db.Column(db.String(500), nullable=False)
    vehicle_make = db.Column(db.String(100))
    vehicle_model = db.Column(db.String(100))
    seller_type = db.Column(db.String(20))
    seller_name = db.Column(db.String(200))
    seller_phone = db.Column(db.String(50))
    seller_email = db.Column(db.String(200))
    prompt_used = db.Column(db.Text, nullable=False)
    generated_text = db.Column(db.Text, nullable=False)
    edited_text = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default="draft")
    llm_model = db.Column(db.String(80), nullable=False)
    tokens_used = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    scan = db.relationship("ScanLog", backref="email_drafts")

    def __repr__(self):
        return f"<EmailDraft {self.vehicle_make} {self.vehicle_model} [{self.status}]>"
