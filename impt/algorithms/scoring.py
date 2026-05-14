"""impt/algorithms/scoring.py — Algorithm 1: Multi-Factor Priority Scoring."""
from __future__ import annotations
from typing import List, Optional, Dict
from impt.models.mutant import Mutant
from impt.models.project import Project, DEFAULT_OPERATOR_MULTIPLIERS


class MultiFactorScorer:
    def __init__(self, project: Project):
        self.weights     = project.config.factor_weights
        self.multipliers = project.config.operator_multipliers

    def score_population(self, mutants: List[Mutant]) -> None:
        if not mutants:
            return
        stats = self._compute_stats(mutants)
        for m in mutants:
            m.priority_score, m.priority_explanation = self._score(m, stats)

    def score_single(self, mutant: Mutant, pop_stats: Optional[Dict] = None) -> None:
        stats = pop_stats or {}
        mutant.priority_score, mutant.priority_explanation = self._score(mutant, stats)

    def _compute_stats(self, mutants: List[Mutant]) -> Dict:
        def rng(attr):
            vals = [getattr(m.factors, attr) for m in mutants]
            lo, hi = min(vals), max(vals)
            return (lo, hi) if hi != lo else (lo, lo + 1e-9)

        return {
            "hist":  rng("historical_effectiveness"),
            "cc":    rng("cyclomatic_complexity"),
            "cog":   rng("cognitive_complexity"),
            "nest":  rng("nesting_depth"),
            "sec":   rng("security_score"),
            "days":  rng("days_since_change"),
            "bug":   rng("bug_density"),
        }

    def _norm(self, val: float, lo: float, hi: float) -> float:
        rng = hi - lo
        if rng < 1e-9:
            return 0.5
        return (val - lo) / rng

    def _score(self, m: Mutant, stats: Dict):
        f = m.factors
        w = self.weights

        n_hist  = self._norm(f.historical_effectiveness, *stats.get("hist", (0, 1)))
        n_cc    = self._norm(f.cyclomatic_complexity,    *stats.get("cc",   (1, 20)))
        n_cog   = self._norm(f.cognitive_complexity,     *stats.get("cog",  (1, 12)))
        n_nest  = self._norm(f.nesting_depth,            *stats.get("nest", (0, 5)))
        n_sec   = self._norm(f.security_score,           *stats.get("sec",  (0, 1)))
        n_days  = self._norm(f.days_since_change,        *stats.get("days", (0, 60)))
        n_bug   = self._norm(f.bug_density,              *stats.get("bug",  (0, 5)))

        n_complexity = (n_cc + n_cog + n_nest) / 3.0
        n_recency    = 1.0 - n_days  # recently changed = higher priority

        raw = (
            w.get("historical_effectiveness", 0.30) * n_hist +
            w.get("code_complexity",          0.25) * n_complexity +
            w.get("security_criticality",     0.20) * n_sec +
            w.get("change_recency",           0.15) * n_recency +
            w.get("bug_history",              0.10) * n_bug
        )

        multiplier = self.multipliers.get(m.operator.value, 1.0)
        score = min(10.0, raw * multiplier * 10.0)

        explanation = (
            f"Score {score:.2f}/10 | "
            f"HistEff={n_hist:.2f} ComplexIdx={n_complexity:.2f} "
            f"SecScore={n_sec:.2f} Recency={n_recency:.2f} BugDens={n_bug:.2f} "
            f"OpMult={multiplier:.1f}x"
        )
        return score, explanation
