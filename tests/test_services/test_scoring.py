"""Tests for the scoring service."""

from app.filters.base import FilterResult
from app.services.scoring import calculate_score


class TestCalculateScore:
    def test_empty_results(self):
        score, is_partial = calculate_score([])
        assert score == 0
        assert is_partial is True

    def test_all_pass(self):
        results = [
            FilterResult("L1", "pass", 1.0, "OK"),
            FilterResult("L2", "pass", 0.8, "OK"),
            FilterResult("L3", "pass", 1.0, "OK"),
        ]
        score, is_partial = calculate_score(results)
        assert score == 93  # (1.0 + 0.8 + 1.0) / 3 * 100 = 93.33 -> 93
        assert is_partial is False

    def test_with_skip(self):
        results = [
            FilterResult("L1", "pass", 1.0, "OK"),
            FilterResult("L2", "skip", 0.0, "Skipped"),
            FilterResult("L3", "pass", 0.5, "Warning"),
        ]
        score, is_partial = calculate_score(results)
        # Active: L1 (1.0) + L3 (0.5) = 1.5 / 2 * 100 = 75
        assert score == 75
        assert is_partial is True

    def test_all_skipped(self):
        results = [
            FilterResult("L1", "skip", 0.0, "Skipped"),
            FilterResult("L2", "skip", 0.0, "Skipped"),
        ]
        score, is_partial = calculate_score(results)
        assert score == 0
        assert is_partial is True

    def test_all_fail(self):
        results = [
            FilterResult("L1", "fail", 0.0, "Bad"),
            FilterResult("L2", "fail", 0.0, "Bad"),
        ]
        score, is_partial = calculate_score(results)
        assert score == 0
        assert is_partial is False

    def test_mixed_results(self):
        results = [
            FilterResult("L1", "pass", 1.0, "OK"),
            FilterResult("L2", "warning", 0.5, "Attention"),
            FilterResult("L3", "fail", 0.0, "Red flag"),
            FilterResult("L4", "pass", 0.9, "OK"),
        ]
        score, is_partial = calculate_score(results)
        # (1.0 + 0.5 + 0.0 + 0.9) / 4 * 100 = 60
        assert score == 60
        assert is_partial is False
