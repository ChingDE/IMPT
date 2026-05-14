"""api/schemas/schemas.py — Pydantic request/response models."""
from __future__ import annotations

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, field_validator


# ── Auth ───────────────────────────────────────────────────────────────────────

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    organization: Optional[str] = Field(default=None, max_length=255)

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        import re
        if not re.match(r"^[A-Za-z\s\-]+$", v):
            raise ValueError("Only letters, spaces, and hyphens allowed")
        return v.strip()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        import re
        errors = []
        if len(v) < 8:
            errors.append("at least 8 characters")
        if not re.search(r"[A-Z]", v):
            errors.append("one uppercase letter")
        if not re.search(r"[a-z]", v):
            errors.append("one lowercase letter")
        if not re.search(r"\d", v):
            errors.append("one number")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            errors.append("one special character")
        if errors:
            raise ValueError(f"Password must contain: {', '.join(errors)}")
        return v


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class ChangeAdminPasswordRequest(BaseModel):
    new_username: str
    new_password: str
    new_email: EmailStr


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)
    confirm_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        import re
        errors = []
        if not re.search(r"[A-Z]", v): errors.append("one uppercase letter")
        if not re.search(r"[a-z]", v): errors.append("one lowercase letter")
        if not re.search(r"\d", v): errors.append("one number")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v): errors.append("one special character")
        if errors:
            raise ValueError(f"Password must contain: {', '.join(errors)}")
        return v


class UserOut(BaseModel):
    id: str
    email: str
    first_name: str
    last_name: str
    organization: Optional[str] = None
    role: str
    is_active: bool
    is_verified: bool
    username: Optional[str] = None
    must_change_password: bool = False
    last_login_at: Optional[datetime] = None
    created_at: datetime
    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class MessageOut(BaseModel):
    message: str


# ── Profile ────────────────────────────────────────────────────────────────────

class ProfileUpdate(BaseModel):
    first_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    last_name: Optional[str]  = Field(default=None, min_length=1, max_length=100)
    organization: Optional[str] = Field(default=None, max_length=255)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)
    confirm_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        import re
        errors = []
        if not re.search(r"[A-Z]", v): errors.append("one uppercase letter")
        if not re.search(r"[a-z]", v): errors.append("one lowercase letter")
        if not re.search(r"\d", v): errors.append("one number")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v): errors.append("one special character")
        if errors:
            raise ValueError(f"Password must contain: {', '.join(errors)}")
        return v


class UserStatsOut(BaseModel):
    total_sessions: int
    total_jobs: int
    avg_mutation_score: float
    avg_time_saved: float
    avg_correlation: float
    total_time_saved_minutes: float = 0.0


# ── Test Sessions ──────────────────────────────────────────────────────────────

class SessionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    language: str  # java | javascript
    description: Optional[str] = Field(default=None, max_length=500)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        import re
        if not re.match(r"^[A-Za-z0-9\s\-_]+$", v):
            raise ValueError("Session name can only contain letters, numbers, spaces, hyphens, and underscores")
        return v.strip()

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        if v.lower() not in ("java", "javascript"):
            raise ValueError("Language must be 'java' or 'javascript'")
        return v.lower()


class SessionOut(BaseModel):
    id: str
    name: str
    language: str
    description: Optional[str] = None
    status: str
    upload_filename: Optional[str] = None
    upload_size_bytes: Optional[int] = None
    file_count: Optional[int] = None
    loc: Optional[int] = None
    test_count: Optional[int] = None
    detected_framework: Optional[str] = None
    selected_operators: Optional[str] = None
    time_budget_minutes: Optional[int] = None
    run_comparison: bool = True
    run_operator_based: bool = True
    estimated_mutant_count: Optional[int] = None
    recommended_budget_min: Optional[int] = None
    recommended_budget_max: Optional[int] = None
    share_token: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class SessionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)


class OperatorConfigRequest(BaseModel):
    selected_operators: List[str]  # e.g. ["AOR", "ROR", "COR"]


class TimeBudgetRequest(BaseModel):
    time_budget_minutes: int = Field(ge=5, le=120)
    run_comparison: bool = True
    run_operator_based: bool = True


# ── Jobs ───────────────────────────────────────────────────────────────────────

class JobStatusOut(BaseModel):
    id: str
    session_id: str
    strategy: str
    status: str
    time_budget_seconds: int
    optimizer_strategy: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
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
    session_id: str
    strategy: str
    status: str
    time_budget_seconds: int
    optimizer_strategy: str
    total_mutants: int
    selected_mutants: int
    executed_mutants: int
    killed_mutants: int
    mutation_score: float
    estimated_score: float
    ci_lower: float
    ci_upper: float
    time_saved_pct: float
    subsumption_reduction_pct: float
    execution_time_seconds: float
    created_at: datetime
    completed_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class MutantOut(BaseModel):
    id: str
    mutant_hash: str
    operator: str
    file: str
    line: int
    original_code: Optional[str] = None
    mutated_code: Optional[str] = None
    status: str
    priority_score: float
    execution_time: float
    explanation: Optional[str] = None
    killing_test: Optional[str] = None
    model_config = {"from_attributes": True}


# ── Admin ──────────────────────────────────────────────────────────────────────

class AdminUserOut(BaseModel):
    id: str
    email: str
    first_name: str
    last_name: str
    organization: Optional[str] = None
    role: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None
    last_active_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class AdminStatsOut(BaseModel):
    total_users: int
    total_sessions: int
    total_jobs: int
    completed_jobs: int
    active_users_7d: int


class SystemConfigOut(BaseModel):
    key: str
    value: str
    description: Optional[str] = None
    updated_at: datetime
    model_config = {"from_attributes": True}


class SystemConfigUpdate(BaseModel):
    value: str


class AuditLogOut(BaseModel):
    id: str
    user_id: Optional[str] = None
    level: str
    category: str
    action: str
    message: str
    ip_address: Optional[str] = None
    outcome: str
    created_at: datetime
    model_config = {"from_attributes": True}
