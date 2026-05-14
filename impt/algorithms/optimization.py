"""impt/algorithms/optimization.py — Algorithm 3: Time-Budget Optimizer (Knapsack)."""
from __future__ import annotations
from enum import Enum
from typing import List, Tuple
from impt.models.mutant import Mutant


class SelectionStrategy(Enum):
    AUTO              = "AUTO"
    DYNAMIC_PROGRAMMING = "DP"
    GREEDY            = "GREEDY"


class TimeBudgetOptimizer:
    DP_THRESHOLD = 1000

    def __init__(self, time_budget_seconds: int,
                 strategy: SelectionStrategy = SelectionStrategy.AUTO):
        self.budget   = time_budget_seconds
        self.strategy = strategy

    def select(self, mutants: List[Mutant]) -> List[Mutant]:
        if not mutants:
            return []
        fits_all = sum(m.execution_time for m in mutants) <= self.budget
        if fits_all:
            return list(mutants)

        use_dp = (
            self.strategy == SelectionStrategy.DYNAMIC_PROGRAMMING or
            (self.strategy == SelectionStrategy.AUTO and len(mutants) <= self.DP_THRESHOLD and self.budget <= 3600)
        )
        return self._dp(mutants) if use_dp else self._greedy(mutants)

    def _dp(self, mutants: List[Mutant]) -> List[Mutant]:
        W      = int(self.budget)
        n      = len(mutants)
        times  = [max(1, int(m.execution_time)) for m in mutants]
        scores = [int(m.priority_score * 10000) for m in mutants]

        dp = [0] * (W + 1)
        for i in range(n):
            for w in range(W, times[i] - 1, -1):
                dp[w] = max(dp[w], dp[w - times[i]] + scores[i])

        # Backtrack
        table = [[0] * (W + 1) for _ in range(n + 1)]
        for i in range(1, n + 1):
            for w in range(W + 1):
                if times[i-1] <= w:
                    table[i][w] = max(table[i-1][w], table[i-1][w-times[i-1]] + scores[i-1])
                else:
                    table[i][w] = table[i-1][w]

        selected = []
        w = W
        for i in range(n, 0, -1):
            if table[i][w] != table[i-1][w]:
                selected.append(mutants[i-1])
                w -= times[i-1]
        return selected

    def _greedy(self, mutants: List[Mutant]) -> List[Mutant]:
        ranked   = sorted(mutants, key=lambda m: m.efficiency_ratio(), reverse=True)
        selected = []
        remaining = float(self.budget)
        for m in ranked:
            if m.execution_time <= remaining:
                selected.append(m)
                remaining -= m.execution_time
        return selected
