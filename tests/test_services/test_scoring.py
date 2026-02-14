"""Tests for the weighted scoring service."""

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
        # Weighted: L1(1.0*1.0) + L2(2.0*0.8) + L3(1.5*1.0) = 4.1 / 4.5 = 91
        assert score == 91
        assert is_partial is False

    def test_with_skip(self):
        results = [
            FilterResult("L1", "pass", 1.0, "OK"),
            FilterResult("L2", "skip", 0.0, "Skipped"),
            FilterResult("L3", "pass", 0.5, "Warning"),
        ]
        score, is_partial = calculate_score(results)
        # L2 skip: poids 2.0 dans denominateur, 0 dans numerateur
        # Weighted: L1(1.0*1.0) + L3(1.5*0.5) = 1.75 / 4.5 = 39
        assert score == 39
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
        # Weighted: L1(1.0) + L2(2.0*0.5) + L3(0) + L4(2.0*0.9) = 3.8 / 6.5 = 58
        assert score == 58
        assert is_partial is False


class TestWeightedScoringScenarios:
    """Tests des scenarios reels avec le scoring pondere."""

    def test_unknown_model_penalized(self):
        """Reproduit le cas Mini Autres: modele inconnu + 3 filtres skip → ~49%."""
        results = [
            FilterResult("L1", "warning", 0.8, "Infos manquantes"),
            FilterResult("L2", "warning", 0.3, "Modele non reconnu"),
            FilterResult("L3", "pass", 1.0, "Coherent"),
            FilterResult("L4", "skip", 0.0, "Modele non reconnu"),
            FilterResult("L5", "skip", 0.0, "Modele non reconnu"),
            FilterResult("L6", "skip", 0.0, "Pas de telephone"),
            FilterResult("L7", "pass", 0.9, "SIRET ok"),
            FilterResult("L8", "pass", 1.0, "Pas d'import"),
            FilterResult("L9", "warning", 0.75, "Pas de telephone"),
        ]
        score, is_partial = calculate_score(results)
        # 5.925 / 12.0 = 49.4 → 49
        assert score == 49
        assert is_partial is True

    def test_critical_skip_below_70(self):
        """L4/L5 skip (pas de data prix) → score < 70 meme si le reste est bon."""
        results = [
            FilterResult("L1", "pass", 0.9, "OK"),
            FilterResult("L2", "pass", 1.0, "Reconnu"),
            FilterResult("L3", "pass", 1.0, "Coherent"),
            FilterResult("L4", "skip", 0.0, "Pas de donnees"),
            FilterResult("L5", "skip", 0.0, "Pas de donnees"),
        ]
        score, is_partial = calculate_score(results)
        # L1(0.9) + L2(2.0) + L3(1.5) = 4.4 / 8.0 = 55
        assert score == 55
        assert score < 70
        assert is_partial is True

    def test_all_nine_pass(self):
        """Tous les 9 filtres pass → score >= 95."""
        results = [
            FilterResult("L1", "pass", 1.0, "OK"),
            FilterResult("L2", "pass", 1.0, "Reconnu"),
            FilterResult("L3", "pass", 1.0, "Coherent"),
            FilterResult("L4", "pass", 1.0, "Prix ok"),
            FilterResult("L5", "pass", 1.0, "Stats ok"),
            FilterResult("L6", "pass", 1.0, "Telephone ok"),
            FilterResult("L7", "pass", 0.9, "SIRET ok"),
            FilterResult("L8", "pass", 1.0, "Pas d'import"),
            FilterResult("L9", "pass", 1.0, "Tout bon"),
        ]
        score, is_partial = calculate_score(results)
        # 11.9 / 12.0 = 99
        assert score >= 95
        assert is_partial is False

    def test_private_seller_no_phone_still_green(self):
        """Vendeur prive (L7 skip), pas de tel (L6 skip) mais reste raisonnable."""
        results = [
            FilterResult("L1", "warning", 0.8, "Infos manquantes"),
            FilterResult("L2", "pass", 1.0, "Reconnu"),
            FilterResult("L3", "pass", 1.0, "Coherent"),
            FilterResult("L4", "pass", 1.0, "Prix ok"),
            FilterResult("L5", "pass", 1.0, "Stats ok"),
            FilterResult("L6", "skip", 0.0, "Pas de telephone"),
            FilterResult("L7", "skip", 0.0, "Vendeur particulier"),
            FilterResult("L8", "pass", 1.0, "Pas d'import"),
            FilterResult("L9", "warning", 0.75, "Pas de telephone"),
        ]
        score, is_partial = calculate_score(results)
        # (0.8 + 2.0 + 1.5 + 2.0 + 1.5 + 0 + 0 + 1.0 + 1.125) / 12.0 = 83
        assert score >= 75
        assert score <= 90
        assert is_partial is True
