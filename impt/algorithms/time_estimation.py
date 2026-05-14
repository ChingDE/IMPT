"""impt/algorithms/time_estimation.py — Algorithm 5: Execution Time Estimator."""
from __future__ import annotations
from typing import Dict, List, Tuple
from impt.models.mutant import Mutant
from impt.models.project import Project

OP_MULTIPLIERS: Dict[str, float] = {
    "SDL": 1.3, "AOR": 1.1, "ROR": 1.1, "COR": 1.0,
    "LCR": 1.0, "SOR": 0.9, "VDL": 1.2, "ODL": 1.1,
    "UOI": 0.7, "NULL_RETURN": 0.9, "NEGATE_RETURN": 0.9,
}
SAFETY_MARGIN     = 1.15
FLOOR_SECONDS     = 1.0
CC_THRESHOLD      = 10
CC_ADJUSTMENT_PCT = 0.05


class ExecutionTimeEstimator:
    def __init__(self, project: Project):
        self.project    = project
        self._cache:    Dict[str, float]            = {}
        self._observed: List[Tuple[float, float]]   = []

    def estimate(self, mutant: Mutant) -> float:
        cache_key = f"{mutant.operator.value}:{mutant.location.key()}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        base   = (self.project.loc * self.project.base_execution_time_per_loc() +
                  self.project.test_count * 0.05)
        op_mul = OP_MULTIPLIERS.get(mutant.operator.value, 1.0)
        est    = base * op_mul

        cc = mutant.factors.cyclomatic_complexity
        if cc > CC_THRESHOLD:
            est *= (1 + (cc - CC_THRESHOLD) * CC_ADJUSTMENT_PCT)

        if len(self._observed) >= 10:
            actual_times    = [a for _, a in self._observed]
            predicted_times = [p for p, _ in self._observed]
            ratio = (sum(actual_times) / sum(predicted_times))
            ratio = max(0.5, min(2.0, ratio))
            est  *= ratio

        est = max(FLOOR_SECONDS, est * SAFETY_MARGIN)
        self._cache[cache_key] = est
        return est

    def estimate_population(self, mutants: List[Mutant]) -> None:
        for m in mutants:
            m.execution_time = self.estimate(m)

    def record_actual(self, predicted: float, actual: float) -> None:
        self._observed.append((predicted, actual))
        if len(self._observed) > 100:
            self._observed.pop(0)
