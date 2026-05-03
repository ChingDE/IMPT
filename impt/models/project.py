"""
impt/models/project.py
Project and configuration model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional
from impt.models.mutant import MutationOperator


class MutationFramework(str, Enum):
    PIT     = "PIT"      # Java
    STRYKER = "STRYKER"  # JavaScript / TypeScript


# Default operator weights recommended by manuscript (Just et al., 2014)
DEFAULT_OPERATOR_MULTIPLIERS: Dict[str, float] = {
    MutationOperator.AOR.value:           1.0,
    MutationOperator.ROR.value:           1.8,   # strongest predictor
    MutationOperator.ABS.value:           1.6,   # conditional boundary
    MutationOperator.COR.value:           0.9,
    MutationOperator.LCR.value:           1.2,
    MutationOperator.SOR.value:           0.8,
    MutationOperator.UOI.value:           0.7,
    MutationOperator.SDL.value:           1.3,
    MutationOperator.VDL.value:           1.1,
    MutationOperator.ODL.value:           1.0,
    MutationOperator.NEGATE_RETURN.value: 1.4,
    MutationOperator.NULL_RETURN.value:   1.2,
}

# Default factor weights from Table 1 of manuscript
DEFAULT_FACTOR_WEIGHTS: Dict[str, float] = {
    "historical_effectiveness": 0.30,
    "code_complexity":          0.25,
    "security_criticality":     0.20,
    "change_recency":           0.15,
    "bug_history":              0.10,
}


@dataclass
class ProjectConfig:
    """User-supplied configuration for a mutation testing session."""
    time_budget_seconds: int = 1800          # 30 minutes default
    target_correlation: float = 0.95
    confidence_level: float = 0.95
    factor_weights: Dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_FACTOR_WEIGHTS)
    )
    operator_multipliers: Dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_OPERATOR_MULTIPLIERS)
    )
    enabled_operators: Optional[List[str]] = None    # None = all enabled
    jaccard_threshold: float = 0.90          # Subsumption similarity threshold
    use_dynamic_programming: bool = True     # True = DP; False = greedy only
    dp_size_threshold: int = 1000            # Switch to greedy above this


@dataclass
class Project:
    """Represents an uploaded project to be mutation-tested."""
    name: str
    framework: MutationFramework
    source_dir: str
    test_dir: str
    loc: int = 0              # Lines of code (populated by scanner)
    test_count: int = 0       # Number of test cases
    config: ProjectConfig = field(default_factory=ProjectConfig)
    history_db: Optional[str] = None   # Path to SQLite history file

    def base_execution_time_per_loc(self) -> float:
        """Estimated seconds per LOC for this framework."""
        if self.framework == MutationFramework.PIT:
            return 0.015    # ~15 ms/LOC for Java
        return 0.012        # ~12 ms/LOC for JavaScript
