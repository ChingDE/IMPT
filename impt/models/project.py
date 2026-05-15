"""impt/models/project.py"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


class MutationFramework(Enum):
    PIT     = "PIT"
    STRYKER = "STRYKER"


DEFAULT_FACTOR_WEIGHTS: Dict[str, float] = {
    "historical_effectiveness": 0.30,
    "code_complexity":          0.25,
    "security_criticality":     0.20,
    "change_recency":           0.15,
    "bug_history":              0.10,
}

DEFAULT_OPERATOR_MULTIPLIERS: Dict[str, float] = {
    "AOR": 1.2, "ROR": 1.8, "ABS": 1.6, "COR": 1.3,
    "LCR": 1.1, "SOR": 1.0, "UOI": 0.7, "SDL": 1.0,
    "VDL": 0.9, "ODL": 0.9, "NEGATE_RETURN": 1.4, "NULL_RETURN": 1.3,
}


@dataclass
class ProjectConfig:
    time_budget_seconds: int               = 1200
    jaccard_threshold:   float             = 0.90
    factor_weights:      Dict[str, float]  = field(default_factory=lambda: dict(DEFAULT_FACTOR_WEIGHTS))
    operator_multipliers: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_OPERATOR_MULTIPLIERS))
    dp_size_threshold:   int               = 1000
    confidence_level:    float             = 0.95

    def __post_init__(self):
        total = sum(self.factor_weights.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"Factor weights must sum to 1.0, got {total:.4f}")


@dataclass
class Project:
    name:       str
    framework:  MutationFramework
    source_dir: str
    test_dir:   str
    loc:        int               = 5000
    test_count: int               = 100
    config:     ProjectConfig     = field(default_factory=ProjectConfig)

    def base_execution_time_per_loc(self) -> float:
        # Estimate based on empirical data:
        # seconds_per_mutant ≈ (test_count × avg_test_ms / 1000) / stryker_workers
        # Stryker uses 4 workers by default; avg JS test ~50-100ms, Java ~200-500ms
        # This gives ~0.5-2s per mutant for typical projects
        # The actual measured time from a completed run overrides this in tasks.py
        return 0.003 if self.framework == MutationFramework.PIT else 0.002

