"""
impt/models/mutant.py
Core data model representing a single mutant.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Set


class MutationOperator(str, Enum):
    """Mutation operators supported by IMPT."""
    # Arithmetic
    AOR = "AOR"   # Arithmetic Operator Replacement  (+, -, *, /)
    # Relational
    ROR = "ROR"   # Relational Operator Replacement  (<, >, <=, >=, ==, !=)
    # Conditional boundary
    ABS = "ABS"   # Absolute Value Insertion / Conditional Boundary
    # Conditional / logical
    COR = "COR"   # Conditional Operator Replacement (&&, ||)
    LCR = "LCR"   # Logical Connector Replacement
    # Shift
    SOR = "SOR"   # Shift Operator Replacement
    # Unary
    UOI = "UOI"   # Unary Operator Insertion  (!x, -x)
    # Statement
    SDL = "SDL"   # Statement Deletion
    VDL = "VDL"   # Variable Deletion
    ODL = "ODL"   # Operator Deletion
    # Null / return
    NEGATE_RETURN = "NEGATE_RETURN"  # negate boolean return
    NULL_RETURN   = "NULL_RETURN"    # return null instead of value


class ExecutionStatus(str, Enum):
    PENDING   = "PENDING"
    KILLED    = "KILLED"
    SURVIVED  = "SURVIVED"
    EQUIVALENT = "EQUIVALENT"   # detected as equivalent; excluded from score
    TIMEOUT   = "TIMEOUT"
    ERROR     = "ERROR"


@dataclass
class CodeLocation:
    """Pinpoints where in the source the mutation lives."""
    file: str
    line: int
    column: int = 0
    method: Optional[str] = None
    class_name: Optional[str] = None

    def __str__(self) -> str:
        return f"{self.file}:{self.line}"

    def key(self) -> str:
        return f"{self.file}:{self.line}:{self.column}"


@dataclass
class PriorityFactors:
    """
    Raw (un-normalised) values for the five scoring factors.
    All values are floats in their natural units:
      - historical_effectiveness : kill-rate  [0, 1]
      - cyclomatic_complexity     : integer count (raw)
      - cognitive_complexity      : integer count (raw)
      - nesting_depth             : integer (raw)
      - security_score            : 0 (none) or 1 (security-critical path)
      - days_since_change         : float days (raw; higher = older)
      - bug_density               : defects per KLOC (raw)
    """
    historical_effectiveness: float = 0.5   # default: neutral
    cyclomatic_complexity: float    = 1.0
    cognitive_complexity: float     = 1.0
    nesting_depth: float            = 1.0
    security_score: float           = 0.0
    days_since_change: float        = 30.0  # default: 30 days old
    bug_density: float              = 0.0


@dataclass
class Mutant:
    """
    A single mutant produced by applying one mutation operator to a
    source code location.

    Fields
    ------
    id              : unique identifier (auto-generated from content hash)
    operator        : which mutation operator was applied
    location        : where in the source code
    original_code   : the original code fragment (string)
    mutated_code    : the mutated code fragment (string)
    status          : execution outcome
    execution_time  : wall-clock seconds to run test suite against this mutant
    priority_score  : composite priority score [0, 10]
    priority_explanation : human-readable breakdown of the score
    factors         : raw factor values used for scoring
    test_coverage   : set of test IDs that cover this mutant's location
    """
    operator: MutationOperator
    location: CodeLocation
    original_code: str
    mutated_code: str

    # Set after execution
    status: ExecutionStatus = ExecutionStatus.PENDING
    execution_time: float = 0.0

    # Set by scoring engine
    priority_score: float = 0.0
    priority_explanation: str = ""

    # Raw factor values (populated from static analysis / history)
    factors: PriorityFactors = field(default_factory=PriorityFactors)

    # Test coverage (set of test-case identifiers covering this location)
    test_coverage: Set[str] = field(default_factory=set)

    # Auto-generated
    id: str = field(init=False)

    def __post_init__(self) -> None:
        self.id = self._compute_id()

    def _compute_id(self) -> str:
        raw = f"{self.operator.value}|{self.location.key()}|{self.original_code}|{self.mutated_code}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------
    @property
    def is_killed(self) -> bool:
        return self.status == ExecutionStatus.KILLED

    @property
    def is_survived(self) -> bool:
        return self.status == ExecutionStatus.SURVIVED

    @property
    def is_equivalent(self) -> bool:
        return self.status == ExecutionStatus.EQUIVALENT

    @property
    def counts_in_score(self) -> bool:
        """True if this mutant should be counted in the mutation score denominator."""
        return self.status not in (
            ExecutionStatus.EQUIVALENT,
            ExecutionStatus.ERROR,
            ExecutionStatus.PENDING,
        )

    def efficiency_ratio(self) -> float:
        """Priority per unit execution time (used by knapsack sorter)."""
        t = max(self.execution_time, 0.001)
        return self.priority_score / t

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Mutant):
            return NotImplemented
        return self.id == other.id

    def __repr__(self) -> str:
        return (
            f"Mutant(id={self.id!r}, op={self.operator.value}, "
            f"loc={self.location}, score={self.priority_score:.2f}, "
            f"status={self.status.value})"
        )
