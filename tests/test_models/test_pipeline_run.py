"""Tests du modele PipelineRun."""

from datetime import datetime, timezone

from app.models.pipeline_run import PipelineRun


class TestPipelineRunModel:
    """Tests du modele PipelineRun."""

    def test_create_pipeline_run(self, app, db):
        """Creer un PipelineRun et verifier les champs."""
        with app.app_context():
            run = PipelineRun(
                name="test_pipeline",
                status="success",
                count=42,
                started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                finished_at=datetime(2026, 1, 1, 0, 5, 0, tzinfo=timezone.utc),
            )
            db.session.add(run)
            db.session.commit()

            fetched = PipelineRun.query.filter_by(name="test_pipeline").first()
            assert fetched is not None
            assert fetched.status == "success"
            assert fetched.count == 42

    def test_duration_seconds(self):
        """La propriete duration_seconds retourne la duree en secondes."""
        run = PipelineRun(
            name="test_duration",
            status="success",
            started_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 1, 1, 0, 1, 30, tzinfo=timezone.utc),
        )
        assert run.duration_seconds == 90.0

    def test_duration_none_when_running(self):
        """duration_seconds est None si le pipeline n'est pas termine."""
        run = PipelineRun(
            name="test_running",
            status="running",
            started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        assert run.duration_seconds is None

    def test_repr(self):
        """Le repr est lisible."""
        run = PipelineRun(name="test_repr", status="failure")
        assert "test_repr" in repr(run)
        assert "failure" in repr(run)
