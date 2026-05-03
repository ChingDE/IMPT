"""
tests/unit/test_extrapolation.py
Unit tests for Algorithm 4 — Statistical Extrapolation.
"""

import math
import pytest

from impt.algorithms.extrapolation import StatisticalExtrapolator
from impt.models.mutant import ExecutionStatus
from tests.conftest import make_mutant


@pytest.fixture
def extrapolator():
    return StatisticalExtrapolator(confidence_level=0.95)


def _mark_killed(m, killed: bool):
    m.status = ExecutionStatus.KILLED if killed else ExecutionStatus.SURVIVED
    return m


class TestEstimateFromCounts:
    def test_basic_proportion(self, extrapolator):
        est = extrapolator.estimate_from_counts(killed=70, total=100)
        assert math.isclose(est.sample_score, 0.70, abs_tol=1e-9)
        assert math.isclose(est.estimated_score, 0.70, abs_tol=1e-9)

    def test_ci_bounds_ordered(self, extrapolator):
        est = extrapolator.estimate_from_counts(killed=50, total=100)
        assert est.lower_bound < est.estimated_score < est.upper_bound

    def test_ci_bounds_within_01(self, extrapolator):
        for k in [0, 1, 99, 100]:
            est = extrapolator.estimate_from_counts(killed=k, total=100)
            assert 0.0 <= est.lower_bound <= 1.0
            assert 0.0 <= est.upper_bound <= 1.0

    def test_zero_killed(self, extrapolator):
        est = extrapolator.estimate_from_counts(killed=0, total=50)
        assert est.sample_score == 0.0
        assert est.lower_bound >= 0.0

    def test_all_killed(self, extrapolator):
        est = extrapolator.estimate_from_counts(killed=100, total=100)
        assert est.sample_score == 1.0
        assert est.upper_bound <= 1.0

    def test_zero_total_raises(self, extrapolator):
        with pytest.raises((ValueError, ZeroDivisionError)):
            extrapolator.estimate_from_counts(killed=0, total=0)

    def test_confidence_level_stored(self, extrapolator):
        est = extrapolator.estimate_from_counts(killed=50, total=100)
        assert est.confidence_level == 0.95

    def test_sample_size_stored(self, extrapolator):
        est = extrapolator.estimate_from_counts(killed=40, total=80)
        assert est.sample_size == 80


class TestEstimateFromMutants:
    def test_all_killed(self, extrapolator):
        mutants = [_mark_killed(make_mutant(line=i), True) for i in range(10)]
        est = extrapolator.estimate(mutants)
        assert math.isclose(est.sample_score, 1.0)

    def test_none_killed(self, extrapolator):
        mutants = [_mark_killed(make_mutant(line=i), False) for i in range(10)]
        est = extrapolator.estimate(mutants)
        assert math.isclose(est.sample_score, 0.0)

    def test_half_killed(self, extrapolator):
        mutants = [_mark_killed(make_mutant(line=i), i % 2 == 0) for i in range(10)]
        est = extrapolator.estimate(mutants)
        assert math.isclose(est.sample_score, 0.5, abs_tol=0.01)

    def test_equivalent_excluded(self, extrapolator):
        mutants = [_mark_killed(make_mutant(line=i), True) for i in range(8)]
        equiv = make_mutant(line=99)
        equiv.status = ExecutionStatus.EQUIVALENT
        mutants.append(equiv)
        est = extrapolator.estimate(mutants)
        assert est.sample_size == 8   # equiv excluded

    def test_empty_mutant_list(self, extrapolator):
        est = extrapolator.estimate([])
        assert est.sample_score == 0.0
        assert est.sample_size == 0

    def test_only_equivalent_mutants(self, extrapolator):
        mutants = [make_mutant(line=i) for i in range(5)]
        for m in mutants:
            m.status = ExecutionStatus.EQUIVALENT
        est = extrapolator.estimate(mutants)
        assert est.sample_size == 0


class TestWilsonInterval:
    """Validate Wilson CI properties against known values."""

    def test_95_ci_width_n100(self, extrapolator):
        """For p=0.5, n=100 the 95% Wilson CI should be roughly ±0.098."""
        est = extrapolator.estimate_from_counts(killed=50, total=100)
        width = est.upper_bound - est.lower_bound
        assert 0.15 < width < 0.22   # ~0.196

    def test_wider_ci_for_smaller_n(self, extrapolator):
        est_small = extrapolator.estimate_from_counts(killed=5, total=10)
        est_large = extrapolator.estimate_from_counts(killed=50, total=100)
        assert (est_small.upper_bound - est_small.lower_bound) > (
            est_large.upper_bound - est_large.lower_bound
        )

    def test_99_ci_wider_than_95(self):
        e95 = StatisticalExtrapolator(0.95).estimate_from_counts(50, 100)
        e99 = StatisticalExtrapolator(0.99).estimate_from_counts(50, 100)
        w95 = e95.upper_bound - e95.lower_bound
        w99 = e99.upper_bound - e99.lower_bound
        assert w99 > w95


class TestAccuracyTarget:
    """Verify meets_target_correlation helper."""

    def test_within_tolerance(self, extrapolator):
        assert extrapolator.meets_target_correlation(0.78, 0.80, tolerance=0.05)

    def test_outside_tolerance(self, extrapolator):
        assert not extrapolator.meets_target_correlation(0.70, 0.80, tolerance=0.05)

    def test_exact_match(self, extrapolator):
        assert extrapolator.meets_target_correlation(0.80, 0.80)


class TestAsPercentage:
    def test_format_string(self, extrapolator):
        est = extrapolator.estimate_from_counts(75, 100)
        s = est.as_percentage()
        assert "%" in s
        assert "75.0%" in s or "75%" in s
