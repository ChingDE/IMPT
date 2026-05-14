"""impt/models/result.py"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from impt.models.mutant import Mutant


@dataclass
class StratifiedEstimate:
    sample_score:     float
    estimated_score:  float
    lower_bound:      float
    upper_bound:      float
    confidence_level: float
    sample_size:      int
    margin_of_error:  float

    def meets_target_correlation(self, exhaustive_score: float, tolerance: float = 0.05) -> bool:
        return abs(self.estimated_score - exhaustive_score) <= tolerance


@dataclass
class MutationTestResult:
    all_mutants:      List["Mutant"]
    selected_mutants: List["Mutant"]
    executed_mutants: List["Mutant"]
    mutation_score:   float
    estimate:         Optional[StratifiedEstimate] = None
    subsumption_reduction_pct: float = 0.0
    time_saved_pct:            float = 0.0
    total_execution_time:      float = 0.0
    operator_stats:            Dict  = field(default_factory=dict)

    def summary(self) -> str:
        killed   = sum(1 for m in self.executed_mutants if m.is_killed)
        survived = len(self.executed_mutants) - killed
        lines = [
            f"IMPT Mutation Testing Results",
            f"  Total mutants generated : {len(self.all_mutants)}",
            f"  After subsumption       : {len(self.selected_mutants)} ({self.subsumption_reduction_pct:.1f}% reduction)",
            f"  Executed within budget  : {len(self.executed_mutants)}",
            f"  Killed                  : {killed}",
            f"  Survived                : {survived}",
            f"  Mutation score          : {self.mutation_score * 100:.1f}%",
            f"  Time saved              : {self.time_saved_pct:.1f}%",
            f"  Execution time          : {self.total_execution_time:.1f}s",
        ]
        if self.estimate:
            lines.append(
                f"  Estimated score         : {self.estimate.estimated_score * 100:.1f}% "
                f"[{self.estimate.lower_bound * 100:.1f}%–{self.estimate.upper_bound * 100:.1f}%] "
                f"({int(self.estimate.confidence_level * 100)}% CI)"
            )
        return "\n".join(lines)
