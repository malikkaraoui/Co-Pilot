"""Modele AppLog -- alimente le tableau de bord d'administration."""

from datetime import datetime, timezone

from app.extensions import db


class AppLog(db.Model):
    """Entree de journal applicatif pour le monitoring du tableau de bord admin."""

    __tablename__ = "app_logs"

    id = db.Column(db.Integer, primary_key=True)
    level = db.Column(db.String(20), nullable=False)
    module = db.Column(db.String(120))
    message = db.Column(db.Text, nullable=False)
    extra = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<AppLog {self.level} {self.module}>"
