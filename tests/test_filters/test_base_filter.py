"""Tests for BaseFilter and FilterResult."""

import pytest

from app.filters.base import BaseFilter, FilterResult


class StubPassFilter(BaseFilter):
    """Stub filter that always passes."""

    filter_id = "T1"

    def run(self, data):
        return FilterResult(
            filter_id=self.filter_id,
            status="pass",
            score=1.0,
            message="All good",
        )


class StubFailFilter(BaseFilter):
    """Stub filter that always fails."""

    filter_id = "T2"

    def run(self, data):
        return FilterResult(
            filter_id=self.filter_id,
            status="fail",
            score=0.0,
            message="Red flag detected",
            details={"reason": "test"},
        )


class TestFilterResult:
    def test_filter_result_fields(self):
        fr = FilterResult(
            filter_id="L1",
            status="pass",
            score=0.85,
            message="OK",
        )
        assert fr.filter_id == "L1"
        assert fr.status == "pass"
        assert fr.score == 0.85
        assert fr.details is None

    def test_filter_result_with_details(self):
        fr = FilterResult(
            filter_id="L4",
            status="warning",
            score=0.5,
            message="Price above average",
            details={"delta_pct": 12},
        )
        assert fr.details["delta_pct"] == 12


class TestBaseFilter:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            BaseFilter()

    def test_stub_pass_filter(self):
        f = StubPassFilter()
        result = f.run({})
        assert result.filter_id == "T1"
        assert result.status == "pass"
        assert result.score == 1.0

    def test_stub_fail_filter(self):
        f = StubFailFilter()
        result = f.run({})
        assert result.status == "fail"
        assert result.details == {"reason": "test"}

    def test_skip_helper(self):
        f = StubPassFilter()
        result = f.skip("Not applicable")
        assert result.status == "skip"
        assert result.score == 0.0
        assert result.message == "Not applicable"
