"""Tests for FilterEngine."""

from app.errors import FilterError
from app.filters.base import BaseFilter, FilterResult
from app.filters.engine import FilterEngine


class PassFilter(BaseFilter):
    filter_id = "T1"

    def run(self, data):
        return FilterResult(
            filter_id=self.filter_id,
            status="pass",
            score=1.0,
            message="OK",
        )


class WarningFilter(BaseFilter):
    filter_id = "T2"

    def run(self, data):
        return FilterResult(
            filter_id=self.filter_id,
            status="warning",
            score=0.5,
            message="Attention",
        )


class ErrorFilter(BaseFilter):
    """Filter that raises FilterError."""

    filter_id = "T3"

    def run(self, data):
        raise FilterError("Something went wrong")


class TestFilterEngine:
    def test_run_all_empty(self):
        engine = FilterEngine()
        results = engine.run_all({})
        assert results == []

    def test_register_and_count(self):
        engine = FilterEngine()
        engine.register(PassFilter())
        engine.register(WarningFilter())
        assert engine.filter_count == 2

    def test_run_all_parallel(self):
        engine = FilterEngine()
        engine.register(PassFilter())
        engine.register(WarningFilter())
        results = engine.run_all({"test": True})
        assert len(results) == 2
        statuses = {r.filter_id: r.status for r in results}
        assert statuses["T1"] == "pass"
        assert statuses["T2"] == "warning"

    def test_filter_error_produces_skip(self):
        engine = FilterEngine()
        engine.register(PassFilter())
        engine.register(ErrorFilter())
        results = engine.run_all({})
        assert len(results) == 2
        error_result = next(r for r in results if r.filter_id == "T3")
        assert error_result.status == "skip"
        assert error_result.score == 0.0

    def test_results_sorted_by_filter_id(self):
        engine = FilterEngine()
        engine.register(ErrorFilter())  # T3
        engine.register(PassFilter())  # T1
        engine.register(WarningFilter())  # T2
        results = engine.run_all({})
        ids = [r.filter_id for r in results]
        assert ids == ["T1", "T2", "T3"]
