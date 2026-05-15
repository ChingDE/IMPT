"""impt/algorithms/time_estimation.py — Algorithm 5: Execution Time Estimator.

Implements the manuscript specification exactly (Section 3.5.2, Figure 17):
  base_time = 0.015 × LOC  (PIT/Java)
  base_time = 0.012 × LOC  (Stryker/JS)
  test_overhead = 0.05 × test_count
  base_time += test_overhead
  base_time × operator_multiplier × complexity_factor × 1.15 safety margin

Historical calibration: if ≥10 prior runs, apply ratio = mean(actual)/mean(predicted).
Cache: keyed by (project_id, operator, location).
"""
from __future__ import annotations
from typing import Dict, List, Tuple
from impt.models.mutant import Mutant
from impt.models.project import Project, MutationFramework

# Manuscript Table (Figure 17, lines 16-20)
OP_MULTIPLIERS: Dict[str, float] = {
    # Manuscript table (Figure 17, lines 16-20) — operators produced by PIT/Stryker
    "AOR": 1.0,   # PIT + Stryker
    "ROR": 1.1,   # PIT + Stryker
    "COR": 0.9,   # PIT + Stryker
    "LCR": 1.2,   # Stryker only
    "UOI": 0.7,   # PIT + Stryker
    "SDL": 1.3,   # PIT + Stryker
    # Not in manuscript table — reasonable empirical defaults
    "ABS":           1.0,   # PIT only
    "CRP":           1.0,   # Stryker only
    "NULL_RETURN":   0.9,   # PIT + Stryker
    "NEGATE_RETURN": 0.9,   # PIT + Stryker
    # SOR/VDL/ODL omitted — not produced by PIT or Stryker in standard config
}

SAFETY_MARGIN     = 1.15   # manuscript line 41
FLOOR_SECONDS     = 1.0    # manuscript line 44: Max(1, Round(...))
CC_THRESHOLD      = 10     # manuscript line 28
CC_ADJUSTMENT_PCT = 0.05   # manuscript line 29: 5% per complexity point above 10
CALIBRATION_MIN_SAMPLES = 10  # manuscript line 37


class ExecutionTimeEstimator:
    """Algorithm 5 — exact manuscript implementation."""

    def __init__(self, project: Project):
        self.project    = project
        self._cache:    Dict[str, float]          = {}
        self._observed: List[Tuple[float, float]] = []  # (predicted, actual)

    def estimate(self, mutant: Mutant) -> float:
        # manuscript line 2-4: check cache
        cache_key = f"{mutant.operator.value}:{mutant.location.key()}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # manuscript lines 6-13: base time from project characteristics
        if self.project.framework == MutationFramework.PIT:
            base_time = 0.015 * self.project.loc       # Java: ~15ms per LOC
        else:
            base_time = 0.012 * self.project.loc       # JS:   ~12ms per LOC

        # manuscript line 13-14: test suite overhead — 50ms per test
        test_overhead = 0.05 * self.project.test_count
        base_time += test_overhead

        # manuscript lines 21-25: operator-specific multiplier
        op_key     = mutant.operator.value if hasattr(mutant.operator, "value") else str(mutant.operator)
        multiplier = OP_MULTIPLIERS.get(op_key, 1.0)
        base_time *= multiplier

        # manuscript lines 27-32: complexity factor
        cc = mutant.factors.cyclomatic_complexity
        if cc > CC_THRESHOLD:
            complexity_factor = 1.0 + (CC_ADJUSTMENT_PCT * (cc - CC_THRESHOLD))
        else:
            complexity_factor = 1.0
        base_time *= complexity_factor

        # manuscript lines 34-39: historical calibration if ≥10 prior runs
        if len(self._observed) >= CALIBRATION_MIN_SAMPLES:
            actual_times    = [a for _, a in self._observed]
            predicted_times = [p for p, _ in self._observed]
            calibration_ratio = (sum(actual_times) / max(sum(predicted_times), 0.001))
            calibration_ratio = max(0.5, min(2.0, calibration_ratio))  # clamp to [0.5, 2.0]
            base_time *= calibration_ratio

        # manuscript lines 41-44: safety margin + floor + round
        estimated_time = base_time * SAFETY_MARGIN
        estimated_time = max(FLOOR_SECONDS, round(estimated_time))

        # manuscript line 46: cache result
        self._cache[cache_key] = estimated_time
        return estimated_time

    def estimate_population(self, mutants: List[Mutant]) -> None:
        """Set execution_time on all mutants."""
        for m in mutants:
            m.execution_time = self.estimate(m)

    def record_actual(self, predicted: float, actual: float) -> None:
        """Feed back actual execution time for historical calibration."""
        self._observed.append((predicted, actual))
        if len(self._observed) > 100:
            self._observed.pop(0)
        # Invalidate cache so next estimates use updated calibration
        self._cache.clear()
