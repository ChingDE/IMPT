"""impt/models/mutant.py — Core mutant domain model."""
from __future__ import annotations
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Set


class MutationOperator(Enum):
    AOR           = "AOR"           # Arithmetic Operator Replacement
    ROR           = "ROR"           # Relational Operator Replacement
    ABS           = "ABS"           # Conditional Boundary (Absolute value insertion)
    COR           = "COR"           # Conditional Operator Replacement
    LCR           = "LCR"           # Logical Connector Replacement
    SOR           = "SOR"           # Shift Operator Replacement
    UOI           = "UOI"           # Unary Operator Insertion
    SDL           = "SDL"           # Statement Deletion
    VDL           = "VDL"           # Variable Deletion
    ODL           = "ODL"           # Operator Deletion
    CRP           = "CRP"           # Constant Replacement
    NULL_RETURN   = "NULL_RETURN"   # Null/empty return value
    NEGATE_RETURN = "NEGATE_RETURN" # Negated/primitive return value


class ExecutionStatus(Enum):
    PENDING    = "PENDING"
    KILLED     = "KILLED"
    SURVIVED   = "SURVIVED"
    EQUIVALENT = "EQUIVALENT"
    TIMEOUT    = "TIMEOUT"
    ERROR      = "ERROR"


@dataclass
class CodeLocation:
    file:        str
    line:        int
    column:      int = 0
    method_name: Optional[str] = None
    class_name:  Optional[str] = None

    def key(self) -> str:
        return f"{self.file}:{self.line}:{self.column}"


@dataclass
class PriorityFactors:
    historical_effectiveness: float = 0.5
    cyclomatic_complexity:    float = 5.0
    cognitive_complexity:     float = 3.0
    nesting_depth:            float = 2.0
    security_score:           float = 0.0
    days_since_change:        float = 30.0
    bug_density:              float = 1.0


@dataclass
class Mutant:
    operator:       MutationOperator
    location:       CodeLocation
    original_code:  str
    mutated_code:   str
    factors:        PriorityFactors = field(default_factory=PriorityFactors)
    status:         ExecutionStatus = ExecutionStatus.PENDING
    execution_time: float           = 0.0
    priority_score: float           = 0.0
    priority_explanation: str       = ""
    test_coverage:  Set[str]        = field(default_factory=set)
    killing_test:   Optional[str]   = field(default=None)

    def __post_init__(self):
        raw = f"{self.operator.value}:{self.location.key()}:{self.original_code}:{self.mutated_code}"
        self.id = hashlib.sha256(raw.encode()).hexdigest()[:16]

    @property
    def is_killed(self) -> bool:
        return self.status == ExecutionStatus.KILLED

    @property
    def counts_in_score(self) -> bool:
        return self.status not in (
            ExecutionStatus.EQUIVALENT,
            ExecutionStatus.ERROR,
            ExecutionStatus.PENDING,
        )

    def efficiency_ratio(self) -> float:
        t = max(self.execution_time, 0.001)
        return self.priority_score / t
