"""tests/unit/test_extrapolation.py"""
from impt.algorithms.extrapolation import StatisticalExtrapolator
from impt.models.mutant import ExecutionStatus
from tests.conftest import make_mutant


def test_wilson_ci_within_bounds():
    ext  = StatisticalExtrapolator(0.95)
    mutants = []
    for i in range(50):
        m = make_mutant()
        m.status = ExecutionStatus.KILLED if i % 3 != 0 else ExecutionStatus.SURVIVED
        mutants.append(m)
    result = ext.estimate(mutants)
    assert 0.0 <= result.lower_bound <= result.estimated_score <= result.upper_bound <= 1.0


def test_all_killed_gives_high_score():
    ext  = StatisticalExtrapolator()
    mutants = []
    for _ in range(30):
        m = make_mutant()
        m.status = ExecutionStatus.KILLED
        mutants.append(m)
    result = ext.estimate(mutants)
    assert result.estimated_score > 0.9


def test_empty_gives_zero():
    ext    = StatisticalExtrapolator()
    result = ext.estimate([])
    assert result.estimated_score == 0.0


def test_different_confidence_levels():
    mutants = []
    for i in range(50):
        m = make_mutant()
        m.status = ExecutionStatus.KILLED if i < 35 else ExecutionStatus.SURVIVED
        mutants.append(m)
    ext90  = StatisticalExtrapolator(0.90)
    ext99  = StatisticalExtrapolator(0.99)
    r90    = ext90.estimate(mutants)
    r99    = ext99.estimate(mutants)
    assert (r99.upper_bound - r99.lower_bound) >= (r90.upper_bound - r90.lower_bound)
