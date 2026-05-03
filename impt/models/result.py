"""
impt/models/result.py
Output models produced after a mutation testing session.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from impt.models.mutant import Mutant, ExecutionStatus


@dataclass
class StratifiedEstimate:
    """
    Full-population mutation score estimate produced by the
    Statistical Extrapolation Algorithm (Algorithm 4).
    """
    sample_score: float           # proportion killed in the selected sample
    estimated_score: float        # point estimate (= sample_score for simple CI)
    lower_bound: float            # 95 % CI lower
    upper_bound: float            # 95 % CI upper
    confidence_level: float = 0.95
    sample_size: int = 0
    margin_of_error: float = 0.0

    def as_percentage(self) -> str:
        pct   = round(self.estimated_score * 100, 1)
        lower = round(self.lower_bound     * 100, 1)
        upper = round(self.upper_bound     * 100, 1)
        return (
            f"Estimated Mutation Score: {pct}% "
            f"({int(self.confidence_level*100)}% CI: {lower}% – {upper}%)"
        )


@dataclass
class MutationTestResult:
    """Complete output of one IMPT session."""
    project_name: str
    framework: str

    # Mutant pools
    all_mutants: List[Mutant] = field(default_factory=list)
    selected_mutants: List[Mutant] = field(default_factory=list)
    executed_mutants: List[Mutant] = field(default_factory=list)

    # Performance
    total_execution_time: float = 0.0
    exhaustive_time_estimate: float = 0.0  # estimated if all ran
    time_saved_pct: float = 0.0

    # Score
    mutation_score: float = 0.0           # actual score on selected set
    estimate: Optional[StratifiedEstimate] = None

    # Algorithm diagnostics
    mutants_before_subsumption: int = 0
    mutants_after_subsumption: int = 0
    equivalent_mutants_detected: int = 0
    subsumption_reduction_pct: float = 0.0

    # Correlation with exhaustive (computed externally during validation)
    pearson_r: Optional[float] = None
    spearman_rho: Optional[float] = None

    # Per-operator breakdown
    operator_stats: Dict[str, Dict] = field(default_factory=dict)

    def compute_mutation_score(self) -> float:
        """Recompute mutation score from executed_mutants list."""
        countable = [m for m in self.executed_mutants if m.counts_in_score]
        if not countable:
            return 0.0
        killed = sum(1 for m in countable if m.is_killed)
        self.mutation_score = killed / len(countable)
        return self.mutation_score

    def summary(self) -> str:
        lines = [
            f"=== IMPT Session Report ===",
            f"Project         : {self.project_name}",
            f"Framework       : {self.framework}",
            f"Total mutants   : {len(self.all_mutants)}",
            f"After subsump.  : {self.mutants_after_subsumption}  "
            f"({self.subsumption_reduction_pct:.1f}% reduction)",
            f"Selected        : {len(self.selected_mutants)}",
            f"Executed        : {len(self.executed_mutants)}",
            f"Killed          : {sum(1 for m in self.executed_mutants if m.is_killed)}",
            f"Mutation score  : {self.mutation_score*100:.1f}%",
            f"Execution time  : {self.total_execution_time:.1f}s",
            f"Time saved      : {self.time_saved_pct:.1f}%",
        ]
        if self.estimate:
            lines.append(self.estimate.as_percentage())
        if self.pearson_r is not None:
            lines.append(f"Pearson r       : {self.pearson_r:.4f}")
        return "\n".join(lines)
