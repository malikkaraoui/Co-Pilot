"""Modele base de donnees FilterResult (resultats de filtres persistes)."""

from datetime import datetime, timezone

from app.extensions import db


class FilterResultDB(db.Model):
    """Resultat persiste d'une execution de filtre individuelle."""

    __tablename__ = "filter_results"

    id = db.Column(db.Integer, primary_key=True)
    scan_id = db.Column(db.Integer, db.ForeignKey("scan_logs.id"), nullable=False)
    filter_id = db.Column(db.String(10), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    score = db.Column(db.Float, default=0.0)
    message = db.Column(db.Text)
    details = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<FilterResultDB {self.filter_id} {self.status}>"
