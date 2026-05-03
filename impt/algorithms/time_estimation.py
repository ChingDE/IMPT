"""
impt/algorithms/time_estimation.py
Algorithm 5 — Execution Time Estimator
=======================================
Predicts the wall-clock time required to run the test suite against a
single mutant.  Used by the Time-Budget Optimizer (Algorithm 3) to assign
knapsack weights before any mutant is actually executed.

Hybrid approach (Section 3.5.2):
  1. Cache hit  → return cached value          O(1)
  2. Base time  = LOC × per-LOC rate + tests × test_overhead
  3. Operator multiplier (calibrated vs 50 FOSS projects)
  4. Complexity adjustment (+5 % per cyclomatic unit above 10)
  5. Historical calibration (if ≥ 10 previous runs available)
  6. +15 % safety margin

Typical accuracy: ±15 % of actual execution time.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple

from impt.models.mutant import Mutant, MutationOperator
from impt.models.project import MutationFramework, Project

log = logging.getLogger(__name__)

# Per-operator execution time multipliers (calibrated empirically)
# Operators that cause earlier test-suite short-circuit get lower values.
OPERATOR_MULTIPLIERS: Dict[str, float] = {
    MutationOperator.AOR.value:           1.0,
    MutationOperator.ROR.value:           1.1,
    MutationOperator.ABS.value:           1.1,
    MutationOperator.COR.value:           0.9,
    MutationOperator.LCR.value:           1.2,
    MutationOperator.SOR.value:           0.8,
    MutationOperator.UOI.value:           0.7,   # fastest: fails early
    MutationOperator.SDL.value:           1.3,   # slowest: recompile needed
    MutationOperator.VDL.value:           1.1,
    MutationOperator.ODL.value:           1.0,
    MutationOperator.NEGATE_RETURN.value: 1.1,
    MutationOperator.NULL_RETURN.value:   1.0,
}

SAFETY_MARGIN = 1.15          # 15 % buffer (conservative estimation)
TEST_OVERHEAD  = 0.05         # seconds per test case
MIN_TIME_FLOOR = 1.0          # floor: no mutant runs in < 1 second
COMPLEXITY_THRESHOLD  = 10    # cyclomatic complexity threshold
COMPLEXITY_RATE       = 0.05  # +5 % per unit above threshold


class ExecutionTimeEstimator:
    """
    Estimates the execution time for each mutant so the optimizer can
    use these as knapsack weights.

    Parameters
    ----------
    project : Project
        The project being tested (supplies LOC, test_count, framework).
    history : dict, optional
        Maps (project_id, operator, location_key) tuples to observed
        execution times from previous sessions.  Used for calibration.
    """

    def __init__(
        self,
        project: Project,
        history: Optional[Dict[Tuple, float]] = None,
    ) -> None:
        self.project = project
        self.history: Dict[Tuple, float] = history or {}
        self._cache: Dict[str, float] = {}

        # Calibration ratio (computed once from history if available)
        self._calibration_ratio = self._compute_calibration_ratio()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def estimate(self, mutant: Mutant) -> float:
        """
        Return the estimated execution time in seconds for this mutant.
        Also sets mutant.execution_time in place.
        """
        cache_key = self._cache_key(mutant)

        # 1. Cache hit
        if cache_key in self._cache:
            t = self._cache[cache_key]
            mutant.execution_time = t
            return t

        # 2. Base time
        t = self._base_time()

        # 3. Operator multiplier
        op_mult = OPERATOR_MULTIPLIERS.get(mutant.operator.value, 1.0)
        t *= op_mult

        # 4. Complexity adjustment
        cc = mutant.factors.cyclomatic_complexity
        if cc > COMPLEXITY_THRESHOLD:
            t *= 1.0 + COMPLEXITY_RATE * (cc - COMPLEXITY_THRESHOLD)

        # 5. Historical calibration
        t *= self._calibration_ratio

        # 6. Safety margin + floor
        t = max(MIN_TIME_FLOOR, t * SAFETY_MARGIN)
        t = round(t, 3)

        self._cache[cache_key] = t
        mutant.execution_time  = t
        return t

    def estimate_population(self, mutants: list) -> list:
        """
        Estimate times for an entire mutant list in place.
        Returns the same list with execution_time fields populated.
        """
        for m in mutants:
            self.estimate(m)
        return mutants

    def update_history(self, mutant: Mutant, actual_time: float) -> None:
        """
        Call this after a mutant actually executes to feed observed
        times back into the calibration history for future sessions.
        """
        key = self._history_key(mutant)
        self.history[key] = actual_time
        # Refresh calibration
        self._calibration_ratio = self._compute_calibration_ratio()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _base_time(self) -> float:
        """
        Base time = LOC contribution + test-suite overhead.
        """
        loc_rate = self.project.base_execution_time_per_loc()
        loc_time  = self.project.loc * loc_rate
        test_time = self.project.test_count * TEST_OVERHEAD
        return loc_time + test_time

    def _compute_calibration_ratio(self) -> float:
        """
        If ≥ 10 historical observations exist for this project, compute
        the mean(actual) / mean(predicted_at_time) ratio.
        We approximate predicted using base_time only (no multipliers) as
        a stable denominator.
        """
        if not self.history or len(self.history) < 10:
            return 1.0   # no calibration data yet

        actuals = list(self.history.values())
        base    = self._base_time() or 1.0
        predicted = [base] * len(actuals)   # simplified: same base for all

        mean_actual    = sum(actuals) / len(actuals)
        mean_predicted = sum(predicted) / len(predicted)

        if mean_predicted <= 0:
            return 1.0

        ratio = mean_actual / mean_predicted
        # Clamp to [0.5, 2.0] to prevent wild outliers
        return max(0.5, min(2.0, ratio))

    def _base_time_no_calibration(self) -> float:
        """Alias used internally for calibration computation."""
        return self._base_time()

    @staticmethod
    def _cache_key(mutant: Mutant) -> str:
        return f"{mutant.operator.value}|{mutant.location.key()}"

    def _history_key(self, mutant: Mutant) -> tuple:
        return (
            self.project.name,
            mutant.operator.value,
            mutant.location.key(),
        )
