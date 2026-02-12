"""Tests du context manager track_pipeline."""

import pytest

from app.models.pipeline_run import PipelineRun
from app.services.pipeline_tracker import track_pipeline


class TestTrackPipeline:
    """Tests du suivi de pipeline."""

    def test_successful_pipeline(self, app, db):
        """Un pipeline reussi a status='success'."""
        with app.app_context():
            with track_pipeline("test_success") as tracker:
                tracker.count = 10

            run = PipelineRun.query.filter_by(name="test_success").first()
            assert run is not None
            assert run.status == "success"
            assert run.count == 10
            assert run.finished_at is not None
            assert run.error_message is None

    def test_failed_pipeline(self, app, db):
        """Un pipeline echoue a status='failure' et error_message."""
        with app.app_context():
            with pytest.raises(ValueError, match="boom"):
                with track_pipeline("test_failure") as tracker:
                    tracker.count = 5
                    raise ValueError("boom")

            run = PipelineRun.query.filter_by(name="test_failure").first()
            assert run is not None
            assert run.status == "failure"
            assert run.count == 5
            assert "boom" in run.error_message
            assert run.finished_at is not None

    def test_multiple_runs_tracked(self, app, db):
        """Plusieurs executions du meme pipeline sont toutes tracees."""
        with app.app_context():
            with track_pipeline("test_multi") as t:
                t.count = 1

            with track_pipeline("test_multi") as t:
                t.count = 2

            runs = PipelineRun.query.filter_by(name="test_multi").all()
            assert len(runs) == 2
