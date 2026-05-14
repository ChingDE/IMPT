"""impt/algorithms/extrapolation.py — Algorithm 4: Statistical Extrapolation (Wilson CI)."""
from __future__ import annotations
import math
from typing import List
from impt.models.mutant import Mutant, ExecutionStatus
from impt.models.result import StratifiedEstimate

Z_VALUES = {0.90: 1.645, 0.95: 1.960, 0.99: 2.576}


class StatisticalExtrapolator:
    def __init__(self, confidence_level: float = 0.95):
        self.confidence_level = confidence_level
        self.z = Z_VALUES.get(confidence_level, self._approx_z(confidence_level))

    def estimate(self, executed: List[Mutant]) -> StratifiedEstimate:
        scored = [m for m in executed if m.counts_in_score]
        n      = len(scored)
        if n == 0:
            return StratifiedEstimate(0.0, 0.0, 0.0, 0.0, self.confidence_level, 0, 0.0)

        killed  = sum(1 for m in scored if m.status == ExecutionStatus.KILLED)
        p_hat   = killed / n
        z, z2   = self.z, self.z ** 2

        centre  = (p_hat + z2 / (2 * n)) / (1 + z2 / n)
        half    = z * math.sqrt(p_hat * (1 - p_hat) / n + z2 / (4 * n**2)) / (1 + z2 / n)

        lower   = max(0.0, centre - half)
        upper   = min(1.0, centre + half)

        return StratifiedEstimate(
            sample_score     = p_hat,
            estimated_score  = centre,
            lower_bound      = lower,
            upper_bound      = upper,
            confidence_level = self.confidence_level,
            sample_size      = n,
            margin_of_error  = half,
        )

    @staticmethod
    def _approx_z(p: float) -> float:
        """Beasley-Springer-Moro rational approximation."""
        a = [2.515517, 0.802853, 0.010328]
        b = [1.432788, 0.189269, 0.001308]
        t = math.sqrt(-2 * math.log(1 - p))
        num = a[0] + a[1]*t + a[2]*t**2
        den = 1 + b[0]*t + b[1]*t**2 + b[2]*t**3
        return t - num / den
