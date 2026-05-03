"""
impt/algorithms/scoring.py
Algorithm 1 — Multi-Factor Scoring Engine
=========================================
Implements the priority score calculation from Section 3.5.2 of the
IMPT manuscript.  Combines five weighted factors:

  Factor                 Weight (default)
  ─────────────────────  ────────────────
  Historical Effectiveness   0.30
  Code Complexity            0.25
  Security Criticality       0.20
  Change Recency             0.15
  Bug History                0.10

Each factor is min-max normalised across the full mutant population
before weighting, per Equation (3) of the manuscript.

Complexity is the mean of (cyclomatic + cognitive + nesting_depth)
normalised scores, giving equal sub-weight inside the complexity factor.

Time complexity: O(n) per full population normalisation pass,
                 O(1) per individual mutant score computation.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from impt.models.mutant import Mutant, MutationOperator, PriorityFactors
from impt.models.project import DEFAULT_FACTOR_WEIGHTS, DEFAULT_OPERATOR_MULTIPLIERS


class MultiFactorScorer:
    """
    Assigns a priority score in [0, 10] to every mutant.

    Parameters
    ----------
    factor_weights : dict
        Overrides for the five factor weights (must sum to 1.0).
    operator_multipliers : dict
        Per-operator effectiveness multipliers (from Just et al., 2014).
    """

    SCORE_SCALE = 10.0  # final scores are on a 0–10 scale

    def __init__(
        self,
        factor_weights: Optional[Dict[str, float]] = None,
        operator_multipliers: Optional[Dict[str, float]] = None,
    ) -> None:
        self.factor_weights = factor_weights or dict(DEFAULT_FACTOR_WEIGHTS)
        self.operator_multipliers = operator_multipliers or dict(DEFAULT_OPERATOR_MULTIPLIERS)
        self._validate_weights()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score_population(self, mutants: List[Mutant]) -> List[Mutant]:
        """
        Score an entire population in one pass.
        Normalises factors across the full list, then computes per-mutant
        weighted sum, applies operator multiplier, scales to [0, 10].

        Returns the same list with priority_score and priority_explanation
        fields filled in (mutants are modified in place).
        """
        if not mutants:
            return mutants

        raw = [self._extract_raw(m) for m in mutants]
        norms = self._normalise_population(raw)

        for mutant, norm in zip(mutants, norms):
            score, explanation = self._compute_score(mutant, norm)
            mutant.priority_score = score
            mutant.priority_explanation = explanation

        return mutants

    def score_single(
        self,
        mutant: Mutant,
        population_stats: Optional[Dict[str, Tuple[float, float]]] = None,
    ) -> Tuple[float, str]:
        """
        Score a single mutant.  If population_stats is provided (a dict of
        factor_name -> (min, max) pairs) it is used for normalisation;
        otherwise the mutant's own raw values are used (trivially normalised
        to 0.5 when min == max).

        Returns (priority_score, explanation).
        """
        raw = self._extract_raw(mutant)

        if population_stats:
            norm = {}
            for key, value in raw.items():
                lo, hi = population_stats.get(key, (0.0, 1.0))
                norm[key] = self._minmax(value, lo, hi)
        else:
            norm = {k: 0.5 for k in raw}  # neutral when no population context

        return self._compute_score(mutant, norm)

    def build_population_stats(
        self, mutants: List[Mutant]
    ) -> Dict[str, Tuple[float, float]]:
        """
        Pre-compute (min, max) for each raw factor across a population.
        Useful when you want to score newcomers against an existing population.
        """
        if not mutants:
            return {}
        raws = [self._extract_raw(m) for m in mutants]
        keys = raws[0].keys()
        return {
            k: (min(r[k] for r in raws), max(r[k] for r in raws))
            for k in keys
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_raw(self, mutant: Mutant) -> Dict[str, float]:
        """Pull the six raw numbers out of a mutant's PriorityFactors."""
        f = mutant.factors
        return {
            "historical_effectiveness": f.historical_effectiveness,
            "cyclomatic_complexity":    f.cyclomatic_complexity,
            "cognitive_complexity":     f.cognitive_complexity,
            "nesting_depth":            f.nesting_depth,
            "security_score":           f.security_score,
            "days_since_change":        f.days_since_change,
            "bug_density":              f.bug_density,
        }

    def _normalise_population(
        self, raws: List[Dict[str, float]]
    ) -> List[Dict[str, float]]:
        """Min-max normalise each factor across the population."""
        keys = raws[0].keys()
        mins = {k: min(r[k] for r in raws) for k in keys}
        maxs = {k: max(r[k] for r in raws) for k in keys}
        return [
            {k: self._minmax(r[k], mins[k], maxs[k]) for k in keys}
            for r in raws
        ]

    @staticmethod
    def _minmax(value: float, lo: float, hi: float) -> float:
        if math.isclose(lo, hi):
            return 0.5   # all identical → neutral score
        return max(0.0, min(1.0, (value - lo) / (hi - lo)))

    def _compute_score(
        self, mutant: Mutant, norm: Dict[str, float]
    ) -> Tuple[float, str]:
        """
        Weighted sum → operator multiplier → scale to [0, 10].
        Change recency: higher days_since_change means LOWER priority
        (recently changed code is more fault-prone), so we invert.
        """
        # Code complexity: average of three sub-metrics
        complexity_norm = (
            norm["cyclomatic_complexity"]
            + norm["cognitive_complexity"]
            + norm["nesting_depth"]
        ) / 3.0

        # Recency inversion: older code → lower priority
        recency_norm = 1.0 - norm["days_since_change"]

        weighted = (
            self.factor_weights["historical_effectiveness"] * norm["historical_effectiveness"]
            + self.factor_weights["code_complexity"]        * complexity_norm
            + self.factor_weights["security_criticality"]   * norm["security_score"]
            + self.factor_weights["change_recency"]         * recency_norm
            + self.factor_weights["bug_history"]            * norm["bug_density"]
        )

        # Operator multiplier (from Just et al., 2014)
        multiplier = self.operator_multipliers.get(mutant.operator.value, 1.0)

        raw_score = weighted * multiplier
        # Re-clamp after multiplier application
        raw_score = max(0.0, min(1.0, raw_score))
        priority_score = round(raw_score * self.SCORE_SCALE, 4)

        explanation = self._build_explanation(
            mutant, priority_score, norm, complexity_norm, recency_norm
        )
        return priority_score, explanation

    def _build_explanation(
        self,
        mutant: Mutant,
        score: float,
        norm: Dict[str, float],
        complexity_norm: float,
        recency_norm: float,
    ) -> str:
        reasons = []

        hist = norm["historical_effectiveness"]
        if hist >= 0.8:
            reasons.append(
                f"{mutant.operator.value} operator "
                f"(historical kill-rate: {mutant.factors.historical_effectiveness:.0%})"
            )

        if complexity_norm >= 0.7:
            reasons.append(
                f"high complexity "
                f"(cyclomatic={mutant.factors.cyclomatic_complexity:.0f}, "
                f"cognitive={mutant.factors.cognitive_complexity:.0f})"
            )

        if norm["security_score"] >= 0.5:
            reasons.append("security-critical code section")

        if recency_norm >= 0.8:
            days = int(mutant.factors.days_since_change)
            reasons.append(f"recently modified ({days}d ago)")

        if norm["bug_density"] >= 0.7:
            reasons.append(
                f"high bug density "
                f"({mutant.factors.bug_density:.1f} defects/KLOC)"
            )

        if not reasons:
            reasons.append("baseline priority")

        return f"Priority {score:.2f}/10: " + "; ".join(reasons) + "."

    def _validate_weights(self) -> None:
        total = sum(self.factor_weights.values())
        if not math.isclose(total, 1.0, abs_tol=1e-6):
            raise ValueError(
                f"factor_weights must sum to 1.0, got {total:.6f}"
            )
        required = {
            "historical_effectiveness",
            "code_complexity",
            "security_criticality",
            "change_recency",
            "bug_history",
        }
        missing = required - self.factor_weights.keys()
        if missing:
            raise ValueError(f"Missing factor weight keys: {missing}")
