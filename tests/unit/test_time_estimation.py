"""tests/unit/test_time_estimation.py"""
from impt.algorithms.time_estimation import ExecutionTimeEstimator
from impt.models.mutant import MutationOperator
from tests.conftest import make_mutant, make_project


def test_estimate_returns_positive():
    project   = make_project(loc=5000, tests=100)
    estimator = ExecutionTimeEstimator(project)
    m         = make_mutant()
    t         = estimator.estimate(m)
    assert t >= 1.0


def test_sdl_slower_than_uoi():
    project   = make_project()
    estimator = ExecutionTimeEstimator(project)
    m_sdl     = make_mutant(operator=MutationOperator.SDL)
    m_uoi     = make_mutant(operator=MutationOperator.UOI)
    assert estimator.estimate(m_sdl) > estimator.estimate(m_uoi)


def test_cache_hit():
    project   = make_project()
    estimator = ExecutionTimeEstimator(project)
    m         = make_mutant(line=42)
    t1        = estimator.estimate(m)
    t2        = estimator.estimate(m)
    assert t1 == t2


def test_estimate_population():
    project   = make_project()
    estimator = ExecutionTimeEstimator(project)
    mutants   = [make_mutant(line=i*10) for i in range(10)]
    estimator.estimate_population(mutants)
    assert all(m.execution_time >= 1.0 for m in mutants)


def test_calibration_with_observed():
    project   = make_project()
    estimator = ExecutionTimeEstimator(project)
    for _ in range(15):
        estimator.record_actual(5.0, 10.0)
    m = make_mutant()
    t = estimator.estimate(m)
    assert t > 1.0
