"""
tests/unit/test_scoring.py
Unit tests for Algorithm 1 — Multi-Factor Scoring Engine.
"""

import math
import pytest

from impt.algorithms.scoring import MultiFactorScorer
from impt.models.mutant import MutationOperator, PriorityFactors
from tests.conftest import make_mutant


class TestMultiFactorScorerInit:
    def test_default_weights_sum_to_one(self):
        scorer = MultiFactorScorer()
        total = sum(scorer.factor_weights.values())
        assert math.isclose(total, 1.0, abs_tol=1e-6)

    def test_invalid_weights_raise(self):
        bad_weights = {
            "historical_effectiveness": 0.50,
            "code_complexity":          0.50,
            "security_criticality":     0.10,   # total > 1
            "change_recency":           0.10,
            "bug_history":              0.10,
        }
        with pytest.raises(ValueError, match="sum to 1.0"):
            MultiFactorScorer(factor_weights=bad_weights)

    def test_missing_weight_key_raises(self):
        incomplete = {
            "historical_effectiveness": 0.60,
            "code_complexity":          0.40,
            # missing three keys
        }
        with pytest.raises(ValueError):
            MultiFactorScorer(factor_weights=incomplete)


class TestScoreRange:
    def test_score_in_range(self, sample_population):
        scorer = MultiFactorScorer()
        scorer.score_population(sample_population)
        for m in sample_population:
            assert 0.0 <= m.priority_score <= 10.0, (
                f"Score out of range for {m}: {m.priority_score}"
            )

    def test_empty_population_returns_empty(self):
        scorer = MultiFactorScorer()
        result = scorer.score_population([])
        assert result == []

    def test_single_mutant(self, sample_mutant):
        scorer = MultiFactorScorer()
        scorer.score_population([sample_mutant])
        assert 0.0 <= sample_mutant.priority_score <= 10.0


class TestScoreOrdering:
    def test_high_historical_scores_higher(self):
        """Mutant with 90% historical kill-rate should outscore one with 10%."""
        scorer = MultiFactorScorer()
        high = make_mutant(MutationOperator.ROR, historical=0.9)
        low  = make_mutant(MutationOperator.ROR, historical=0.1, line=99)
        scorer.score_population([high, low])
        assert high.priority_score > low.priority_score

    def test_security_critical_scores_higher(self):
        scorer = MultiFactorScorer()
        sec    = make_mutant(MutationOperator.ROR, security=1.0)
        nonsec = make_mutant(MutationOperator.ROR, security=0.0, line=99)
        scorer.score_population([sec, nonsec])
        assert sec.priority_score > nonsec.priority_score

    def test_recent_change_scores_higher(self):
        """More recent (fewer days) → higher recency → higher score."""
        scorer = MultiFactorScorer()
        recent = make_mutant(MutationOperator.AOR, days=1.0)
        old    = make_mutant(MutationOperator.AOR, days=90.0, line=99)
        scorer.score_population([recent, old])
        assert recent.priority_score > old.priority_score

    def test_high_complexity_scores_higher(self):
        scorer = MultiFactorScorer()
        complex_m = make_mutant(MutationOperator.SDL, cyclomatic=20.0)
        simple_m  = make_mutant(MutationOperator.SDL, cyclomatic=1.0, line=99)
        scorer.score_population([complex_m, simple_m])
        assert complex_m.priority_score > simple_m.priority_score

    def test_ror_multiplier_applied(self):
        """ROR has 1.8× multiplier vs AOR at 1.0× — ROR should score higher."""
        scorer = MultiFactorScorer()
        ror = make_mutant(MutationOperator.ROR, historical=0.5)
        aor = make_mutant(MutationOperator.AOR, historical=0.5, line=99)
        # Give identical factors except operator
        ror.factors = aor.factors.__class__(
            historical_effectiveness=0.5,
            cyclomatic_complexity=5,
            cognitive_complexity=5,
            nesting_depth=2,
            security_score=0.0,
            days_since_change=15,
            bug_density=1.0,
        )
        aor.factors = ror.factors.__class__(
            historical_effectiveness=0.5,
            cyclomatic_complexity=5,
            cognitive_complexity=5,
            nesting_depth=2,
            security_score=0.0,
            days_since_change=15,
            bug_density=1.0,
        )
        scorer.score_population([ror, aor])
        assert ror.priority_score > aor.priority_score


class TestExplanation:
    def test_explanation_non_empty(self, sample_population):
        scorer = MultiFactorScorer()
        scorer.score_population(sample_population)
        for m in sample_population:
            assert len(m.priority_explanation) > 0

    def test_explanation_contains_score(self, sample_population):
        scorer = MultiFactorScorer()
        scorer.score_population(sample_population)
        for m in sample_population:
            assert "Priority" in m.priority_explanation

    def test_security_mentioned_in_explanation(self):
        scorer = MultiFactorScorer()
        m = make_mutant(MutationOperator.ROR, security=1.0, historical=0.95)
        scorer.score_population([m])
        assert "security" in m.priority_explanation.lower()


class TestNormalisation:
    def test_identical_factors_get_neutral_score(self):
        """All mutants identical → min==max → all get 0.5 normalised per factor."""
        scorer = MultiFactorScorer()
        mutants = [make_mutant(MutationOperator.ROR, line=i) for i in range(5)]
        # All have same factors (defaults from make_mutant)
        scorer.score_population(mutants)
        scores = {m.priority_score for m in mutants}
        assert len(scores) == 1  # all identical

    def test_population_stats_single_score(self, sample_mutant):
        scorer = MultiFactorScorer()
        score, expl = scorer.score_single(sample_mutant)
        assert 0.0 <= score <= 10.0
        assert len(expl) > 0

    def test_build_population_stats(self, sample_population):
        scorer = MultiFactorScorer()
        stats = scorer.build_population_stats(sample_population)
        assert "historical_effectiveness" in stats
        lo, hi = stats["historical_effectiveness"]
        assert lo <= hi
