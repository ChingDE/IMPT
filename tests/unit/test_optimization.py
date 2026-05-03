"""
tests/unit/test_optimization.py
Unit tests for Algorithm 3 — Time-Budget Optimizer.
"""

import pytest

from impt.algorithms.optimization import (
    SelectionStrategy,
    TimeBudgetOptimizer,
)
from tests.conftest import make_mutant
from impt.models.mutant import MutationOperator


def _set_times(mutants, times):
    for m, t in zip(mutants, times):
        m.execution_time = t
    return mutants


def _set_scores(mutants, scores):
    for m, s in zip(mutants, scores):
        m.priority_score = s
    return mutants


@pytest.fixture
def optimizer_small():
    return TimeBudgetOptimizer(
        time_budget_seconds=10,
        dp_size_threshold=1000,
        strategy=SelectionStrategy.DYNAMIC_PROGRAMMING,
    )


@pytest.fixture
def optimizer_greedy():
    return TimeBudgetOptimizer(
        time_budget_seconds=10,
        strategy=SelectionStrategy.GREEDY,
    )


class TestDPOptimizer:
    def test_selects_within_budget(self, optimizer_small):
        mutants = [make_mutant(line=i) for i in range(5)]
        _set_times(mutants, [3, 3, 3, 3, 3])  # each takes 3s, budget=10
        _set_scores(mutants, [9, 8, 7, 6, 5])
        result = optimizer_small.select(mutants)
        total_t = sum(m.execution_time for m in result.selected)
        assert total_t <= 10
        assert len(result.selected) == 3   # 3×3=9 ≤ 10

    def test_highest_priority_selected(self, optimizer_small):
        mutants = [make_mutant(line=i) for i in range(3)]
        _set_times(mutants, [5, 5, 5])   # budget=10 → max 2
        _set_scores(mutants, [9, 1, 1])
        result = optimizer_small.select(mutants)
        assert any(m.priority_score == 9.0 for m in result.selected)

    def test_empty_input(self, optimizer_small):
        result = optimizer_small.select([])
        assert result.selected == []
        assert result.total_priority == 0.0

    def test_all_fit_in_budget(self, optimizer_small):
        mutants = [make_mutant(line=i) for i in range(3)]
        _set_times(mutants, [2, 2, 2])   # 6s total < 10s budget
        _set_scores(mutants, [5, 5, 5])
        result = optimizer_small.select(mutants)
        assert len(result.selected) == 3

    def test_none_fit_in_budget(self):
        opt = TimeBudgetOptimizer(time_budget_seconds=2, strategy=SelectionStrategy.DYNAMIC_PROGRAMMING)
        mutants = [make_mutant(line=i) for i in range(3)]
        _set_times(mutants, [5, 5, 5])   # all cost 5s > 2s budget
        result = opt.select(mutants)
        assert len(result.selected) == 0

    def test_optimal_selection_knapsack_classic(self):
        """Classic knapsack test: items (value, weight) = (6,2),(10,4),(12,6) budget=10.
           Optimal: (10,4)+(12,6)=22 in 10s. Greedy by ratio: 6/2=3, 10/4=2.5, 12/6=2.
           DP should find optimal."""
        opt = TimeBudgetOptimizer(time_budget_seconds=10, strategy=SelectionStrategy.DYNAMIC_PROGRAMMING)
        m1 = make_mutant(line=1); m1.priority_score = 6.0;  m1.execution_time = 2
        m2 = make_mutant(line=2); m2.priority_score = 10.0; m2.execution_time = 4
        m3 = make_mutant(line=3); m3.priority_score = 12.0; m3.execution_time = 6
        result = opt.select([m1, m2, m3])
        assert abs(result.total_priority - 22.0) < 0.1
        assert result.strategy_used == SelectionStrategy.DYNAMIC_PROGRAMMING

    def test_no_optimality_gap_for_dp(self, optimizer_small):
        mutants = [make_mutant(line=i) for i in range(3)]
        _set_times(mutants, [3, 3, 3])
        _set_scores(mutants, [5, 5, 5])
        result = optimizer_small.select(mutants)
        assert result.optimality_gap_pct is None   # DP is exact


class TestGreedyOptimizer:
    def test_selects_within_budget(self, optimizer_greedy):
        mutants = [make_mutant(line=i) for i in range(5)]
        _set_times(mutants, [3, 3, 3, 3, 3])
        _set_scores(mutants, [9, 8, 7, 6, 5])
        result = optimizer_greedy.select(mutants)
        total_t = sum(m.execution_time for m in result.selected)
        assert total_t <= 10

    def test_greedy_reports_gap(self, optimizer_greedy):
        mutants = [make_mutant(line=i) for i in range(4)]
        _set_times(mutants, [3, 3, 3, 3])
        _set_scores(mutants, [9, 8, 7, 6])
        result = optimizer_greedy.select(mutants)
        assert result.optimality_gap_pct is not None
        assert result.optimality_gap_pct >= 0.0

    def test_strategy_is_greedy(self, optimizer_greedy):
        mutants = [make_mutant(line=i) for i in range(3)]
        _set_times(mutants, [2, 2, 2])
        _set_scores(mutants, [5, 4, 3])
        result = optimizer_greedy.select(mutants)
        assert result.strategy_used == SelectionStrategy.GREEDY


class TestAutoStrategy:
    def test_auto_chooses_dp_for_small(self):
        opt = TimeBudgetOptimizer(
            time_budget_seconds=60,
            dp_size_threshold=100,
            strategy=SelectionStrategy.AUTO,
        )
        mutants = [make_mutant(line=i) for i in range(10)]  # 10 < 100
        _set_times(mutants, [5] * 10)
        _set_scores(mutants, [float(i) for i in range(10)])
        result = opt.select(mutants)
        assert result.strategy_used == SelectionStrategy.DYNAMIC_PROGRAMMING

    def test_auto_chooses_greedy_for_large(self):
        opt = TimeBudgetOptimizer(
            time_budget_seconds=60,
            dp_size_threshold=5,   # low threshold
            strategy=SelectionStrategy.AUTO,
        )
        mutants = [make_mutant(line=i) for i in range(10)]  # 10 > 5
        _set_times(mutants, [3] * 10)
        _set_scores(mutants, [float(i) for i in range(10)])
        result = opt.select(mutants)
        assert result.strategy_used == SelectionStrategy.GREEDY


class TestEdgeCases:
    def test_zero_time_mutant_gets_floor(self):
        opt = TimeBudgetOptimizer(time_budget_seconds=10, strategy=SelectionStrategy.GREEDY)
        m = make_mutant(line=1)
        m.execution_time = 0.0   # invalid
        m.priority_score = 9.0
        result = opt.select([m])
        assert len(result.selected) == 1
        assert result.selected[0].execution_time >= 1.0

    def test_single_mutant_exactly_fits(self):
        opt = TimeBudgetOptimizer(time_budget_seconds=5, strategy=SelectionStrategy.DYNAMIC_PROGRAMMING)
        m = make_mutant(line=1)
        m.execution_time = 5.0
        m.priority_score = 7.0
        result = opt.select([m])
        assert len(result.selected) == 1

    def test_invalid_budget_raises(self):
        with pytest.raises(ValueError):
            TimeBudgetOptimizer(time_budget_seconds=0)
