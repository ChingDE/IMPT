"""
impt/algorithms/optimization.py
Algorithm 3 — Time-Budget Optimizer (0/1 Knapsack)
===================================================
Implements knapsack-based mutant selection from Section 3.5.2.

Strategy selection (per manuscript):
  - n ≤ dp_size_threshold AND budget ≤ 3600 s → Dynamic Programming  O(n·T)
  - Otherwise                                  → Greedy approximation O(n log n)

The DP solution is optimal.
The greedy solution sorts by priority/time ratio (value density) and is
guaranteed within ~10% of optimal for typical mutation testing instances
(Martello & Toth, 1990; Delgado-Perez et al., 2018).
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import List, NamedTuple, Optional, Tuple

from impt.models.mutant import Mutant

log = logging.getLogger(__name__)

DP_MAX_BUDGET_SECONDS = 3600     # 60-minute cap for DP solvability
DP_TIME_GRANULARITY   = 1        # discretise budget to nearest second


class SelectionStrategy(str, Enum):
    DYNAMIC_PROGRAMMING = "DP"
    GREEDY              = "GREEDY"
    AUTO                = "AUTO"   # choose based on problem size


class SelectionResult(NamedTuple):
    selected: List[Mutant]
    strategy_used: SelectionStrategy
    total_priority: float
    total_time: float
    optimality_gap_pct: Optional[float]  # None for DP (exact)
    wall_time_seconds: float             # time taken by the optimizer itself


class TimeBudgetOptimizer:
    """
    Selects the mutant subset that maximises total priority score while
    keeping total estimated execution time within the user-defined budget.

    Parameters
    ----------
    time_budget_seconds : int
        Hard wall-clock budget for mutation testing execution.
    dp_size_threshold : int
        Switch to greedy when mutant count exceeds this value.
    strategy : SelectionStrategy
        Force a particular strategy (default AUTO).
    """

    def __init__(
        self,
        time_budget_seconds: int = 1800,
        dp_size_threshold: int = 1000,
        strategy: SelectionStrategy = SelectionStrategy.AUTO,
    ) -> None:
        if time_budget_seconds <= 0:
            raise ValueError("time_budget_seconds must be positive")
        self.time_budget_seconds = time_budget_seconds
        self.dp_size_threshold   = dp_size_threshold
        self.strategy            = strategy

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def select(self, mutants: List[Mutant]) -> SelectionResult:
        """
        Select the best mutant subset within the time budget.

        Each mutant must have execution_time > 0 (set by ExecutionTimeEstimator
        before this step).  Mutants with execution_time == 0 receive a default
        estimate of 1 second to avoid divide-by-zero.
        """
        if not mutants:
            return SelectionResult([], SelectionStrategy.AUTO, 0.0, 0.0, None, 0.0)

        # Guard: ensure every mutant has a positive execution time
        safe_mutants = self._ensure_positive_times(mutants)

        strategy = self._choose_strategy(safe_mutants)

        t0 = time.perf_counter()
        if strategy == SelectionStrategy.DYNAMIC_PROGRAMMING:
            selected, total_p, total_t = self._dp_select(safe_mutants)
            gap = None
        else:
            selected, total_p, total_t = self._greedy_select(safe_mutants)
            gap = self._estimate_optimality_gap(safe_mutants, total_p)

        elapsed = time.perf_counter() - t0
        log.info(
            "Optimizer [%s]: selected %d/%d mutants | "
            "priority=%.2f | time=%.1fs | optimizer_time=%.3fs",
            strategy.value, len(selected), len(safe_mutants),
            total_p, total_t, elapsed,
        )
        return SelectionResult(selected, strategy, total_p, total_t, gap, elapsed)

    # ------------------------------------------------------------------
    # Strategy chooser
    # ------------------------------------------------------------------

    def _choose_strategy(self, mutants: List[Mutant]) -> SelectionStrategy:
        if self.strategy != SelectionStrategy.AUTO:
            return self.strategy
        n = len(mutants)
        b = self.time_budget_seconds
        if n <= self.dp_size_threshold and b <= DP_MAX_BUDGET_SECONDS:
            return SelectionStrategy.DYNAMIC_PROGRAMMING
        return SelectionStrategy.GREEDY

    # ------------------------------------------------------------------
    # Dynamic Programming — exact O(n × T)
    # ------------------------------------------------------------------

    def _dp_select(
        self, mutants: List[Mutant]
    ) -> Tuple[List[Mutant], float, float]:
        """
        Classic 0/1 Knapsack DP.
        Execution times are discretised to integer seconds.
        Priority scores are scaled ×1000 and rounded to integers for the
        DP table (restores as float on backtrack).
        """
        n = len(mutants)
        T = self.time_budget_seconds  # capacity in seconds (integer)

        # Discretise weights (execution times) to integers
        weights = [max(1, round(m.execution_time)) for m in mutants]
        # Scale values to integers (×10 000 for precision)
        values  = [round(m.priority_score * 10_000) for m in mutants]

        # DP table: dp[i][t] = max total value using first i mutants, budget t
        # Use 1-D rolling array for memory efficiency
        dp = [0] * (T + 1)

        for i in range(n):
            wi = weights[i]
            vi = values[i]
            # Traverse backwards to prevent item reuse
            for t in range(T, wi - 1, -1):
                dp[t] = max(dp[t], dp[t - wi] + vi)

        # ─── Backtrack to find which mutants were selected ─────────────
        # Rebuild the full 2-D table (only needed for backtracking)
        dp2 = [[0] * (T + 1) for _ in range(n + 1)]
        for i in range(1, n + 1):
            wi = weights[i - 1]
            vi = values[i - 1]
            for t in range(T + 1):
                if wi <= t:
                    dp2[i][t] = max(dp2[i - 1][t], dp2[i - 1][t - wi] + vi)
                else:
                    dp2[i][t] = dp2[i - 1][t]

        selected: List[Mutant] = []
        t = T
        for i in range(n, 0, -1):
            if dp2[i][t] != dp2[i - 1][t]:
                selected.append(mutants[i - 1])
                t -= weights[i - 1]

        total_p = sum(m.priority_score for m in selected)
        total_t = sum(m.execution_time for m in selected)
        return selected, total_p, total_t

    # ------------------------------------------------------------------
    # Greedy approximation — O(n log n) after sort
    # ------------------------------------------------------------------

    def _greedy_select(
        self, mutants: List[Mutant]
    ) -> Tuple[List[Mutant], float, float]:
        """
        Sort by priority-per-second ratio descending, greedily add mutants
        that still fit in the remaining budget.
        """
        sorted_m = sorted(mutants, key=lambda m: m.efficiency_ratio(), reverse=True)

        selected: List[Mutant] = []
        remaining = float(self.time_budget_seconds)

        for m in sorted_m:
            if m.execution_time <= remaining:
                selected.append(m)
                remaining -= m.execution_time
            if remaining <= 0:
                break

        total_p = sum(m.priority_score for m in selected)
        total_t = sum(m.execution_time for m in selected)
        return selected, total_p, total_t

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_positive_times(mutants: List[Mutant]) -> List[Mutant]:
        for m in mutants:
            if m.execution_time <= 0:
                m.execution_time = 1.0   # 1-second floor
        return mutants

    def _estimate_optimality_gap(
        self, mutants: List[Mutant], achieved_priority: float
    ) -> Optional[float]:
        """
        Loose upper bound on the optimal value via LP relaxation (fractional
        knapsack).  The gap is (upper_bound - achieved) / upper_bound × 100.
        """
        sorted_m = sorted(mutants, key=lambda m: m.efficiency_ratio(), reverse=True)
        remaining = float(self.time_budget_seconds)
        upper_bound = 0.0
        for m in sorted_m:
            if m.execution_time <= remaining:
                upper_bound += m.priority_score
                remaining   -= m.execution_time
            else:
                # Take fractional portion
                upper_bound += m.priority_score * (remaining / m.execution_time)
                break

        if upper_bound <= 0:
            return 0.0
        gap = (upper_bound - achieved_priority) / upper_bound * 100
        return max(0.0, round(gap, 2))
