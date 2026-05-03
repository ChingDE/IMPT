"""
api/schemas/schemas.py
Pydantic v2 request/response schemas.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# ─────────────────────────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: Optional[str] = None
    role: str = "student"

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in ("student", "professional", "admin"):
            raise ValueError("role must be student, professional, or admin")
        return v


class UserOut(BaseModel):
    id: str
    email: str
    full_name: Optional[str]
    role: str
    is_active: bool
    created_at: datetime
    username: Optional[str] = None
    must_change_password: bool = False

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ─────────────────────────────────────────────────────────────────────────────
# Projects
# ─────────────────────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    framework: str
    loc: int = Field(default=0, ge=0)
    test_count: int = Field(default=0, ge=0)
    is_foss: bool = False
    description: Optional[str] = None

    @field_validator("framework")
    @classmethod
    def validate_framework(cls, v: str) -> str:
        if v.upper() not in ("PIT", "STRYKER"):
            raise ValueError("framework must be PIT or STRYKER")
        return v.upper()


class ProjectOut(BaseModel):
    id: str
    owner_id: str
    name: str
    framework: str
    loc: int
    test_count: int
    is_foss: bool
    description: Optional[str]
    upload_path: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Jobs
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_FACTOR_WEIGHTS = {
    "historical_effectiveness": 0.30,
    "code_complexity":          0.25,
    "security_criticality":     0.20,
    "change_recency":           0.15,
    "bug_history":              0.10,
}


class JobCreate(BaseModel):
    project_id: str
    time_budget_seconds: int = Field(
        default=1800, ge=60, le=3600,
        description="Time budget in seconds (60–3600)"
    )
    optimizer_strategy: str = Field(
        default="AUTO",
        description="AUTO | DP | GREEDY"
    )
    jaccard_threshold: float = Field(
        default=0.90, ge=0.5, le=1.0,
        description="Subsumption similarity threshold"
    )
    factor_weights: Optional[Dict[str, float]] = Field(
        default=None,
        description="Override default factor weights (must sum to 1.0)"
    )

    @field_validator("optimizer_strategy")
    @classmethod
    def validate_strategy(cls, v: str) -> str:
        if v.upper() not in ("AUTO", "DP", "GREEDY"):
            raise ValueError("optimizer_strategy must be AUTO, DP, or GREEDY")
        return v.upper()


class JobStatusOut(BaseModel):
    id: str
    project_id: str
    status: str
    celery_task_id: Optional[str]
    time_budget_seconds: int
    optimizer_strategy: str
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]

    # Live metrics — populated progressively as the job runs
    total_mutants: int = 0
    selected_mutants: int = 0
    executed_mutants: int = 0
    killed_mutants: int = 0
    mutation_score: float = 0.0
    time_saved_pct: float = 0.0
    subsumption_reduction_pct: float = 0.0
    execution_time_seconds: float = 0.0

    model_config = {"from_attributes": True}


class JobResultOut(BaseModel):
    id: str
    project_id: str
    status: str
    time_budget_seconds: int
    optimizer_strategy: str

    # Counts
    total_mutants: int
    selected_mutants: int
    executed_mutants: int
    killed_mutants: int

    # Scores
    mutation_score: float
    estimated_score: float
    ci_lower: float
    ci_upper: float

    # Performance
    time_saved_pct: float
    subsumption_reduction_pct: float
    execution_time_seconds: float

    # Timestamps
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Mutant detail
# ─────────────────────────────────────────────────────────────────────────────

class MutantOut(BaseModel):
    id: str
    mutant_hash: str
    operator: str
    file: str
    line: int
    original_code: str
    mutated_code: str
    status: str
    priority_score: float
    execution_time: float
    explanation: Optional[str]

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────────────────────

class HealthOut(BaseModel):
    status: str
    version: str
    db: str
    worker: str
