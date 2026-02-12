"""Modele PipelineRun -- suivi d'execution des pipelines d'enrichissement."""

from datetime import datetime, timezone

from app.extensions import db


class PipelineRun(db.Model):
    """Trace l'execution d'un pipeline (CSV import, seed argus, etc.)."""

    __tablename__ = "pipeline_runs"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False)  # running, success, failure
    count = db.Column(db.Integer, default=0)
    error_message = db.Column(db.Text)
    started_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    finished_at = db.Column(db.DateTime)

    def __repr__(self):
        return f"<PipelineRun {self.name} {self.status}>"

    @property
    def duration_seconds(self) -> float | None:
        """Duree d'execution en secondes, ou None si non termine."""
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None
