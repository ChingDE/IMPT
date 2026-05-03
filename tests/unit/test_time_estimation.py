"""
tests/unit/test_time_estimation.py
Unit tests for Algorithm 5 — Execution Time Estimator.
"""

import pytest

from impt.algorithms.time_estimation import (
    MIN_TIME_FLOOR,
    SAFETY_MARGIN,
    ExecutionTimeEstimator,
)
from impt.models.mutant import MutationOperator
from impt.models.project import MutationFramework, Project, ProjectConfig
from tests.conftest import make_mutant


@pytest.fixture
def java_project():
    cfg = ProjectConfig(time_budget_seconds=300)
    return Project(
        name="java-project",
        framework=MutationFramework.PIT,
        source_dir="src/",
        test_dir="test/",
        loc=10_000,
        test_count=200,
        config=cfg,
    )


@pytest.fixture
def js_project():
    cfg = ProjectConfig(time_budget_seconds=300)
    return Project(
        name="js-project",
        framework=MutationFramework.STRYKER,
        source_dir="src/",
        test_dir="test/",
        loc=10_000,
        test_count=200,
        config=cfg,
    )


class TestBasicEstimation:
    def test_estimate_is_positive(self, java_project):
        est = ExecutionTimeEstimator(java_project)
        m = make_mutant(MutationOperator.ROR)
        t = est.estimate(m)
        assert t > 0

    def test_estimate_sets_mutant_field(self, java_project):
        est = ExecutionTimeEstimator(java_project)
        m = make_mutant(MutationOperator.ROR)
        t = est.estimate(m)
        assert m.execution_time == t

    def test_estimate_above_floor(self, java_project):
        est = ExecutionTimeEstimator(java_project)
        m = make_mutant(MutationOperator.ROR)
        t = est.estimate(m)
        assert t >= MIN_TIME_FLOOR

    def test_cache_returns_same_value(self, java_project):
        est = ExecutionTimeEstimator(java_project)
        m1 = make_mutant(MutationOperator.ROR, line=5)
        m2 = make_mutant(MutationOperator.ROR, line=5)   # same loc, same op
        t1 = est.estimate(m1)
        t2 = est.estimate(m2)
        assert t1 == t2

    def test_different_operators_different_times(self, java_project):
        est = ExecutionTimeEstimator(java_project)
        sdl = make_mutant(MutationOperator.SDL, line=1)   # multiplier 1.3
        uoi = make_mutant(MutationOperator.UOI, line=2)   # multiplier 0.7
        t_sdl = est.estimate(sdl)
        t_uoi = est.estimate(uoi)
        assert t_sdl > t_uoi   # SDL is slower

    def test_java_slower_than_js(self, java_project, js_project):
        """Java per-LOC rate (0.015) > JS (0.012) → Java takes longer."""
        est_java = ExecutionTimeEstimator(java_project)
        est_js   = ExecutionTimeEstimator(js_project)
        m_java = make_mutant(MutationOperator.ROR, line=10)
        m_js   = make_mutant(MutationOperator.ROR, line=10)
        assert est_java.estimate(m_java) > est_js.estimate(m_js)


class TestComplexityAdjustment:
    def test_high_complexity_longer(self, java_project):
        est = ExecutionTimeEstimator(java_project)
        complex_m = make_mutant(MutationOperator.AOR, line=1, cyclomatic=20.0)
        simple_m  = make_mutant(MutationOperator.AOR, line=2, cyclomatic=3.0)
        assert est.estimate(complex_m) > est.estimate(simple_m)

    def test_below_threshold_no_adjustment(self, java_project):
        est = ExecutionTimeEstimator(java_project)
        m_low  = make_mutant(MutationOperator.AOR, line=1, cyclomatic=5.0)
        m_low2 = make_mutant(MutationOperator.AOR, line=2, cyclomatic=10.0)
        # Both below or at threshold → same base (different lines → different cache key)
        t1 = est.estimate(m_low)
        t2 = est.estimate(m_low2)
        # At exactly threshold there's no adjustment; both should be equal
        assert t1 == t2


class TestHistoricalCalibration:
    def test_calibration_applied_after_10_samples(self, java_project):
        # Build 10 fake history entries (actual ≈ 2× predicted)
        base_est = ExecutionTimeEstimator(java_project)
        base_m   = make_mutant(MutationOperator.ROR, line=99)
        base_t   = base_est.estimate(base_m)

        history = {}
        for i in range(10):
            key = ("java-project", MutationOperator.ROR.value, f"Foo.java:1{i}:0")
            history[key] = base_t * 2   # actual times are 2× predicted

        est_calibrated = ExecutionTimeEstimator(java_project, history=history)
        m = make_mutant(MutationOperator.ROR, line=50)
        t_cal = est_calibrated.estimate(m)
        # Calibrated estimate should be larger than uncalibrated
        assert t_cal > base_t

    def test_no_calibration_below_10_samples(self, java_project):
        history = {("java-project", "ROR", "Foo.java:1:0"): 999.0}  # 1 entry
        est = ExecutionTimeEstimator(java_project, history=history)
        assert est._calibration_ratio == 1.0


class TestPopulationEstimate:
    def test_all_mutants_get_time(self, java_project, sample_population):
        est = ExecutionTimeEstimator(java_project)
        est.estimate_population(sample_population)
        for m in sample_population:
            assert m.execution_time >= MIN_TIME_FLOOR

    def test_population_returns_same_list(self, java_project, sample_population):
        est = ExecutionTimeEstimator(java_project)
        returned = est.estimate_population(sample_population)
        assert returned is sample_population


class TestUpdateHistory:
    def test_update_stores_value(self, java_project):
        est = ExecutionTimeEstimator(java_project)
        m = make_mutant(MutationOperator.ROR, line=1)
        est.update_history(m, actual_time=42.0)
        key = (java_project.name, m.operator.value, m.location.key())
        assert est.history[key] == 42.0
