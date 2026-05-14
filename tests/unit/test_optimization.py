"""tests/unit/test_optimization.py"""
from impt.algorithms.optimization import TimeBudgetOptimizer, SelectionStrategy
from impt.models.mutant import ExecutionStatus
from tests.conftest import make_mutant


def test_greedy_stays_within_budget():
    opt     = TimeBudgetOptimizer(60, SelectionStrategy.GREEDY)
    mutants = [make_mutant(execution_time=10.0, score=float(i)) for i in range(20)]
    result  = opt.select(mutants)
    assert sum(m.execution_time for m in result) <= 60


def test_dp_stays_within_budget():
    opt     = TimeBudgetOptimizer(60, SelectionStrategy.DYNAMIC_PROGRAMMING)
    mutants = [make_mutant(execution_time=10.0, score=float(i)) for i in range(10)]
    result  = opt.select(mutants)
    assert sum(m.execution_time for m in result) <= 60


def test_selects_all_if_budget_sufficient():
    opt     = TimeBudgetOptimizer(1000, SelectionStrategy.GREEDY)
    mutants = [make_mutant(execution_time=5.0) for _ in range(10)]
    result  = opt.select(mutants)
    assert len(result) == 10


def test_greedy_prefers_high_efficiency():
    opt  = TimeBudgetOptimizer(15, SelectionStrategy.GREEDY)
    m1   = make_mutant(score=9.0, execution_time=5.0)   # efficiency 1.8
    m2   = make_mutant(score=4.0, execution_time=10.0)  # efficiency 0.4
    result = opt.select([m1, m2])
    assert m1 in result


def test_auto_picks_dp_for_small():
    opt  = TimeBudgetOptimizer(300, SelectionStrategy.AUTO)
    mutants = [make_mutant(execution_time=10.0, score=float(i)) for i in range(50)]
    result  = opt.select(mutants)
    assert sum(m.execution_time for m in result) <= 300


def test_empty_input():
    opt = TimeBudgetOptimizer(100)
    assert opt.select([]) == []
