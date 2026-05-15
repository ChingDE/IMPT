"""tests/unit/test_time_estimation.py — Algorithm 5 tests (manuscript spec)."""
from impt.algorithms.time_estimation import (
    ExecutionTimeEstimator, OP_MULTIPLIERS, SAFETY_MARGIN, FLOOR_SECONDS
)
from impt.models.mutant import MutationOperator
from impt.models.project import MutationFramework
from impt.models.project import MutationFramework
from tests.conftest import make_mutant, make_project


# ── Manuscript formula verification ─────────────────────────────────────────

def test_pit_base_formula():
    """Java: base = 0.015 × LOC + 0.05 × tests, × safety margin."""
    project = make_project(loc=1000, tests=50)
    project.framework = MutationFramework.PIT
    est = ExecutionTimeEstimator(project)
    m = make_mutant(operator=MutationOperator.AOR)  # AOR multiplier = 1.0
    # Expected: (0.015×1000 + 0.05×50) × 1.0 × 1.0 × 1.15 = (15+2.5)×1.15 = 20.125 → round → 20
    t = est.estimate(m)
    assert t == max(FLOOR_SECONDS, round((0.015*1000 + 0.05*50) * 1.0 * 1.0 * SAFETY_MARGIN))


def test_stryker_base_formula():
    """JS: base = 0.012 × LOC + 0.05 × tests, × safety margin."""
    project = make_project(loc=1000, tests=50)
    project.framework = MutationFramework.STRYKER
    est = ExecutionTimeEstimator(project)
    m = make_mutant(operator=MutationOperator.AOR)
    t = est.estimate(m)
    assert t == max(FLOOR_SECONDS, round((0.012*1000 + 0.05*50) * 1.0 * 1.0 * SAFETY_MARGIN))


def test_operator_multipliers_applied():
    """SDL (1.3) should give higher estimate than UOI (0.7)."""
    project = make_project(loc=1000, tests=50)
    est = ExecutionTimeEstimator(project)
    t_sdl = est.estimate(make_mutant(operator=MutationOperator.SDL, line=1))
    t_uoi = est.estimate(make_mutant(operator=MutationOperator.UOI, line=2))
    assert t_sdl > t_uoi


def test_all_manuscript_operators_have_multipliers():
    """All operators in manuscript table must be in OP_MULTIPLIERS."""
    manuscript_ops = {"AOR", "ROR", "COR", "SOR", "LCR", "UOI", "SDL", "VDL", "ODL"}
    for op in manuscript_ops:
        assert op in OP_MULTIPLIERS, f"{op} missing from OP_MULTIPLIERS"


def test_complexity_factor_above_threshold():
    """Cyclomatic > 10 should increase estimate by 5% per point."""
    project = make_project(loc=1000, tests=50)
    est = ExecutionTimeEstimator(project)
    m_low  = make_mutant(cc=5.0,  line=1)
    m_high = make_mutant(cc=15.0, line=2)
    assert est.estimate(m_high) > est.estimate(m_low)


def test_complexity_factor_below_threshold():
    """Cyclomatic ≤ 10 should give factor = 1.0 (no adjustment)."""
    project = make_project(loc=1000, tests=50)
    project.framework = MutationFramework.PIT  # use PIT so formula is 0.015×LOC
    est = ExecutionTimeEstimator(project)
    m_5  = make_mutant(cc=5.0,  line=1)
    m_10 = make_mutant(cc=10.0, line=2)
    base = (0.015*1000 + 0.05*50) * 1.0  # AOR multiplier=1.0, PIT formula
    expected = max(FLOOR_SECONDS, round(base * SAFETY_MARGIN))
    assert est.estimate(m_5)  == expected
    assert est.estimate(m_10) == expected


def test_safety_margin_is_115_percent():
    """Safety margin must be exactly 1.15 per manuscript."""
    assert SAFETY_MARGIN == 1.15


def test_floor_is_one_second():
    """Minimum estimate is 1 second per manuscript."""
    project = make_project(loc=1, tests=1)
    est = ExecutionTimeEstimator(project)
    m = make_mutant()
    assert est.estimate(m) >= FLOOR_SECONDS


def test_cache_returns_same_value():
    """Same operator+location should return cached value."""
    project = make_project()
    est = ExecutionTimeEstimator(project)
    m = make_mutant(line=42)
    assert est.estimate(m) == est.estimate(m)


def test_historical_calibration_after_10_samples():
    """After ≥10 actual observations, calibration ratio is applied."""
    project = make_project(loc=1000, tests=50)
    est = ExecutionTimeEstimator(project)
    # Record 10 samples: actual is 2× predicted
    for _ in range(10):
        est.record_actual(5.0, 10.0)
    m = make_mutant(line=99)
    t = est.estimate(m)
    # Should be higher than without calibration (ratio ~2.0, clamped to 2.0)
    est2 = ExecutionTimeEstimator(project)
    t_uncalibrated = est2.estimate(make_mutant(line=99))
    assert t > t_uncalibrated


def test_no_calibration_before_10_samples():
    """Fewer than 10 samples should not trigger calibration."""
    project = make_project(loc=1000, tests=50)
    est = ExecutionTimeEstimator(project)
    for _ in range(9):
        est.record_actual(5.0, 100.0)  # extreme ratio
    m = make_mutant(line=99)
    est2 = ExecutionTimeEstimator(project)
    # Should be the same as uncalibrated
    assert est.estimate(m) == est2.estimate(make_mutant(line=99))


def test_estimate_population_sets_execution_time():
    """estimate_population sets execution_time on all mutants."""
    project = make_project()
    est = ExecutionTimeEstimator(project)
    mutants = [make_mutant(line=i*10) for i in range(10)]
    est.estimate_population(mutants)
    assert all(m.execution_time >= FLOOR_SECONDS for m in mutants)
