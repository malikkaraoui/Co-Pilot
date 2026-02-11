"""Modeles ScanLog et ScanResult."""

from datetime import datetime, timezone

from app.extensions import db


class ScanLog(db.Model):
    """Journal de chaque scan effectue via l'API."""

    __tablename__ = "scan_logs"

    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500))
    raw_data = db.Column(db.JSON)
    score = db.Column(db.Integer)
    is_partial = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    filter_results = db.relationship("FilterResultDB", backref="scan", lazy="select")

    def __repr__(self):
        return f"<ScanLog {self.id} score={self.score}>"
