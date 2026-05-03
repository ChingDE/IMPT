"""
impt/algorithms/extrapolation.py
Algorithm 4 — Statistical Extrapolation
========================================
Estimates the full-population mutation score from the executed sample
using binomial confidence intervals.

Uses the Wilson score interval with continuity correction
(Agresti & Coull, 1998) rather than the simpler Wald interval, because
the Wilson interval maintains correct coverage even when the proportion
approaches 0 or 1 — a common scenario in mature or immature test suites.

Standard error formula (binomial):
    SE = sqrt(p̂(1 - p̂) / n)

Wilson score interval (approximation):
    centre = (p̂ + z²/2n) / (1 + z²/n)
    half   = z·sqrt(p̂(1-p̂)/n + z²/(4n²)) / (1 + z²/n)
    CI = [centre - half, centre + half]
"""

from __future__ import annotations

import math
from typing import List

from impt.models.mutant import Mutant, ExecutionStatus
from impt.models.result import StratifiedEstimate


# Pre-computed critical values
_Z_TABLE = {
    0.90: 1.645,
    0.95: 1.960,
    0.99: 2.576,
}


class StatisticalExtrapolator:
    """
    Computes an estimated mutation score and confidence interval from a
    sample of executed mutants.

    Parameters
    ----------
    confidence_level : float
        Desired confidence level.  Must be one of 0.90, 0.95, 0.99,
        or a custom value that will use a normal approximation.
    """

    def __init__(self, confidence_level: float = 0.95) -> None:
        if not 0 < confidence_level < 1:
            raise ValueError("confidence_level must be in (0, 1)")
        self.confidence_level = confidence_level
        self._z = self._critical_value(confidence_level)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def estimate(self, executed_mutants: List[Mutant]) -> StratifiedEstimate:
        """
        Compute the estimated mutation score and CI from executed mutants.
        Only mutants that *count* in the score (non-equivalent, non-error)
        are included.

        Returns a StratifiedEstimate with all fields populated.
        """
        countable = [m for m in executed_mutants if m.counts_in_score]
        n = len(countable)

        if n == 0:
            return StratifiedEstimate(
                sample_score=0.0,
                estimated_score=0.0,
                lower_bound=0.0,
                upper_bound=0.0,
                confidence_level=self.confidence_level,
                sample_size=0,
                margin_of_error=0.0,
            )

        killed = sum(1 for m in countable if m.is_killed)
        p_hat  = killed / n

        lower, upper, margin = self._wilson_interval(p_hat, n)

        return StratifiedEstimate(
            sample_score=p_hat,
            estimated_score=p_hat,
            lower_bound=lower,
            upper_bound=upper,
            confidence_level=self.confidence_level,
            sample_size=n,
            margin_of_error=margin,
        )

    def estimate_from_counts(
        self, killed: int, total: int
    ) -> StratifiedEstimate:
        """
        Convenience overload: pass raw counts instead of a mutant list.
        Useful for unit tests and benchmarking.
        """
        if total <= 0:
            raise ValueError("total must be > 0")
        p_hat = killed / total
        lower, upper, margin = self._wilson_interval(p_hat, total)
        return StratifiedEstimate(
            sample_score=p_hat,
            estimated_score=p_hat,
            lower_bound=lower,
            upper_bound=upper,
            confidence_level=self.confidence_level,
            sample_size=total,
            margin_of_error=margin,
        )

    def meets_target_correlation(
        self,
        estimated_score: float,
        exhaustive_score: float,
        tolerance: float = 0.05,
    ) -> bool:
        """
        Returns True if |estimated - exhaustive| ≤ tolerance.
        Used during white-box testing to check the 2-3 pp accuracy target.
        """
        return abs(estimated_score - exhaustive_score) <= tolerance

    # ------------------------------------------------------------------
    # Interval computation
    # ------------------------------------------------------------------

    def _wilson_interval(
        self, p_hat: float, n: int
    ) -> tuple[float, float, float]:
        """
        Wilson score interval (Agresti & Coull, 1998).
        Returns (lower, upper, margin_of_error).
        """
        z  = self._z
        z2 = z * z

        # Wilson centre and half-width
        centre = (p_hat + z2 / (2 * n)) / (1 + z2 / n)
        half   = (
            z
            * math.sqrt(p_hat * (1 - p_hat) / n + z2 / (4 * n * n))
            / (1 + z2 / n)
        )

        lower = max(0.0, centre - half)
        upper = min(1.0, centre + half)
        margin = half  # symmetric around Wilson centre

        return lower, upper, margin

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _critical_value(confidence_level: float) -> float:
        if confidence_level in _Z_TABLE:
            return _Z_TABLE[confidence_level]
        # Approximate using probit (Abramowitz & Stegun 26.2.17)
        p = (1 + confidence_level) / 2
        return StatisticalExtrapolator._probit(p)

    @staticmethod
    def _probit(p: float) -> float:
        """Rational approximation of the standard normal quantile."""
        # Beasley-Springer-Moro algorithm
        a = [2.515517, 0.802853, 0.010328]
        b = [1.432788, 0.189269, 0.001308]
        t = math.sqrt(-2.0 * math.log(1.0 - p if p > 0.5 else p))
        num = a[0] + t * (a[1] + t * a[2])
        den = 1.0 + t * (b[0] + t * (b[1] + t * b[2]))
        z = t - num / den
        return z if p > 0.5 else -z
