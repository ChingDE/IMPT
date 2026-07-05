"""
db/models/orm_models.py
Complete database schema for IMPT v2.

New in v2:
  - User: first_name, last_name, is_verified, failed_login_attempts,
           lockout_until, username, must_change_password
  - EmailVerificationToken
  - PasswordResetToken
  - TestSession  (named sessions with status — replaces anonymous projects)
  - MutationJob  (now linked to TestSession instead of Project)
  - MutantRecord
  - SavedProfile
  - AuditLog
  - SystemConfig
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text,
    JSON, func, Index
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


class Base(DeclarativeBase):
    pass


# ── Users ─────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[str]                  = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str]               = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str]     = mapped_column(String(255), nullable=False)

    # FR011 — first/last name instead of full_name
    first_name: Mapped[str]          = mapped_column(String(100), nullable=False, default="")
    last_name: Mapped[str]           = mapped_column(String(100), nullable=False, default="")
    organization: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    role: Mapped[str]                = mapped_column(String(50), default="user")  # user | admin
    is_active: Mapped[bool]          = mapped_column(Boolean, default=True)

    # FR018 — email verification status
    is_verified: Mapped[bool]        = mapped_column(Boolean, default=False)

    # FR008 / NFR022 — account lockout
    failed_login_attempts: Mapped[int]       = mapped_column(Integer, default=0)
    lockout_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Admin-specific fields
    username: Mapped[Optional[str]]          = mapped_column(String(64), unique=True, index=True, nullable=True)
    must_change_password: Mapped[bool]       = mapped_column(Boolean, default=False)

    # GitHub account linking (panel comment: connect project repository)
    github_token: Mapped[Optional[str]]        = mapped_column(Text, nullable=True)        # encrypted OAuth token
    github_login: Mapped[Optional[str]]        = mapped_column(String(255), nullable=True)
    github_connected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # NFR025 — tracking
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime]     = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime]     = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    # Relationships
    verification_tokens: Mapped[List["EmailVerificationToken"]] = relationship(
        "EmailVerificationToken", back_populates="user", cascade="all, delete-orphan"
    )
    reset_tokens: Mapped[List["PasswordResetToken"]] = relationship(
        "PasswordResetToken", back_populates="user", cascade="all, delete-orphan"
    )
    test_sessions: Mapped[List["TestSession"]] = relationship(
        "TestSession", back_populates="owner", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship(
        "AuditLog", back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_locked_out(self) -> bool:
        if self.lockout_until and self.lockout_until > datetime.utcnow():
            return True
        return False


# ── Email Verification Tokens ─────────────────────────────────────────────────

class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"

    id: Mapped[str]          = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str]     = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token: Mapped[str]       = mapped_column(String(255), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool]       = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    # Rate limiting — FR023
    resend_count: Mapped[int] = mapped_column(Integer, default=0)
    last_resend_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="verification_tokens")


# ── Password Reset Tokens ─────────────────────────────────────────────────────

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[str]          = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str]     = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token: Mapped[str]       = mapped_column(String(255), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool]       = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped["User"] = relationship("User", back_populates="reset_tokens")


# ── Test Sessions ─────────────────────────────────────────────────────────────
# FR051–FR056: Named sessions with status and workflow tracking

class TestSession(Base):
    __tablename__ = "test_sessions"

    id: Mapped[str]              = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_id: Mapped[str]        = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # FR051–FR053
    name: Mapped[str]            = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # FR052
    language: Mapped[str]        = mapped_column(String(20), nullable=False)  # java | javascript

    # FR044, FR056
    status: Mapped[str]          = mapped_column(String(30), default="not_started")
    # not_started | uploaded | configured | ready | running | completed | failed

    # Upload info
    upload_path: Mapped[Optional[str]]   = mapped_column(String(500), nullable=True)
    upload_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    upload_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    file_count: Mapped[Optional[int]]    = mapped_column(Integer, nullable=True)
    loc: Mapped[Optional[int]]           = mapped_column(Integer, nullable=True)
    test_count: Mapped[Optional[int]]    = mapped_column(Integer, nullable=True)
    detected_framework: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Operator config (FR070–FR079)
    selected_operators: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array

    # Time budget (FR080–FR090)
    time_budget_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Strategy selection (redesigned: single strategy + optional exhaustive)
    selected_strategy: Mapped[str]   = mapped_column(String(30), default="impt")  # impt | random | operator_based
    run_exhaustive: Mapped[bool]     = mapped_column(Boolean, default=False)

    # FOSS project (if user selected a pre-loaded project instead of uploading)
    foss_project_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("foss_projects.id"), nullable=True)
    weight_config:   Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON: MCDM weight override

    # Legacy fields kept for backward compat
    run_comparison: Mapped[bool]     = mapped_column(Boolean, default=True)
    run_operator_based: Mapped[bool] = mapped_column(Boolean, default=True)
    # Estimated mutant count (FR080)
    estimated_mutant_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    recommended_budget_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    recommended_budget_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Timestamps
    created_at: Mapped[datetime]      = mapped_column(DateTime(timezone=True), default=_now, index=True)
    updated_at: Mapped[datetime]      = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Shareable link (FR116)
    share_token: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True, index=True)
    share_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    owner: Mapped["User"] = relationship("User", back_populates="test_sessions")
    jobs: Mapped[List["MutationJob"]] = relationship(
        "MutationJob", back_populates="session", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_test_sessions_owner_updated", "owner_id", "updated_at"),
    )


# ── Mutation Jobs ─────────────────────────────────────────────────────────────

class MutationJob(Base):
    __tablename__ = "mutation_jobs"

    id: Mapped[str]          = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str]  = mapped_column(String(36), ForeignKey("test_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_id: Mapped[str]    = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Job type: impt | random | operator_based | exhaustive
    strategy: Mapped[str]    = mapped_column(String(30), default="impt")

    # Config
    time_budget_seconds: Mapped[int]   = mapped_column(Integer, default=1200)
    optimizer_strategy: Mapped[str]    = mapped_column(String(20), default="AUTO")
    jaccard_threshold: Mapped[float]   = mapped_column(Float, default=0.90)
    factor_weights: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    selected_operators: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON

    # Status
    status: Mapped[str]      = mapped_column(String(20), default="PENDING")
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    error_message: Mapped[Optional[str]]  = mapped_column(Text, nullable=True)

    # Results
    total_mutants: Mapped[int]       = mapped_column(Integer, default=0)
    selected_mutants: Mapped[int]    = mapped_column(Integer, default=0)
    executed_mutants: Mapped[int]    = mapped_column(Integer, default=0)
    killed_mutants: Mapped[int]      = mapped_column(Integer, default=0)
    mutation_score: Mapped[float]    = mapped_column(Float, default=0.0)
    estimated_score: Mapped[float]   = mapped_column(Float, default=0.0)
    ci_lower: Mapped[float]          = mapped_column(Float, default=0.0)
    ci_upper: Mapped[float]          = mapped_column(Float, default=0.0)
    time_saved_pct: Mapped[float]    = mapped_column(Float, default=0.0)
    subsumption_reduction_pct: Mapped[float] = mapped_column(Float, default=0.0)
    execution_time_seconds: Mapped[float]    = mapped_column(Float, default=0.0)
    result_json: Mapped[Optional[str]]       = mapped_column(Text, nullable=True)  # JSON

    # Timestamps
    created_at: Mapped[datetime]      = mapped_column(DateTime(timezone=True), default=_now, index=True)
    started_at: Mapped[Optional[datetime]]   = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    session: Mapped["TestSession"] = relationship("TestSession", back_populates="jobs")
    mutant_records: Mapped[List["MutantRecord"]] = relationship(
        "MutantRecord", back_populates="job", cascade="all, delete-orphan"
    )


# ── Mutant Records ────────────────────────────────────────────────────────────

class MutantRecord(Base):
    __tablename__ = "mutant_records"

    id: Mapped[str]          = mapped_column(String(36), primary_key=True, default=_uuid)
    job_id: Mapped[str]      = mapped_column(String(36), ForeignKey("mutation_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    mutant_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    operator: Mapped[str]    = mapped_column(String(50), nullable=False)
    file: Mapped[str]        = mapped_column(String(500), nullable=False)
    line: Mapped[int]        = mapped_column(Integer, nullable=False)
    original_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mutated_code: Mapped[Optional[str]]  = mapped_column(Text, nullable=True)
    status: Mapped[str]      = mapped_column(String(20), nullable=False)
    priority_score: Mapped[float] = mapped_column(Float, default=0.0)
    execution_time: Mapped[float] = mapped_column(Float, default=0.0)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    killing_test: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    job: Mapped["MutationJob"] = relationship("MutationJob", back_populates="mutant_records")


# ── Saved Profiles ────────────────────────────────────────────────────────────

class SavedProfile(Base):
    __tablename__ = "saved_profiles"

    id: Mapped[str]          = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_id: Mapped[str]    = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str]        = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)  # full config as JSON
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    times_used: Mapped[int]  = mapped_column(Integer, default=0)
    avg_score: Mapped[float] = mapped_column(Float, default=0.0)
    avg_time_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


# ── Audit Logs ────────────────────────────────────────────────────────────────
# NFR025, NFR076

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str]          = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    level: Mapped[str]       = mapped_column(String(20), default="INFO")  # INFO | WARNING | ERROR
    category: Mapped[str]    = mapped_column(String(30), nullable=False)  # AUTH | TESTING | SYSTEM | ADMIN
    action: Mapped[str]      = mapped_column(String(100), nullable=False)
    message: Mapped[str]     = mapped_column(Text, nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    outcome: Mapped[str]     = mapped_column(String(20), default="success")  # success | failure
    extra: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON extra data
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    user: Mapped[Optional["User"]] = relationship("User", back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_logs_category_created", "category", "created_at"),
        Index("ix_audit_logs_level_created", "level", "created_at"),
    )


# ── System Config ─────────────────────────────────────────────────────────────
# FR147–FR152

class OperatorStats(Base):
    """Global operator kill rate statistics — updated after every completed run.
    Used to populate historical_effectiveness factor for IMPT scoring.
    Based on empirical data from published mutation testing research as starting point,
    refined by actual run results from all users.
    """
    __tablename__ = "operator_stats"

    operator:      Mapped[str]   = mapped_column(String(50), primary_key=True)
    total_mutants: Mapped[int]   = mapped_column(Integer, default=0)
    killed_mutants:Mapped[int]   = mapped_column(Integer, default=0)
    kill_rate:     Mapped[float] = mapped_column(Float,   default=0.5)
    last_updated:  Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True,
                                                          default=datetime.utcnow,
                                                          onupdate=datetime.utcnow)


class SystemConfig(Base):
    __tablename__ = "system_config"

    key: Mapped[str]    = mapped_column(String(100), primary_key=True)
    value: Mapped[str]  = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_by: Mapped[Optional[str]]  = mapped_column(String(36), nullable=True)
    updated_at: Mapped[datetime]       = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


# ── FOSS Projects ─────────────────────────────────────────────────────────────

class FossProject(Base):
    """Pre-loaded FOSS projects for trust-building and Chapter 4 validation.
    Users can select these instead of uploading their own project.
    Exhaustive baselines are pre-computed and stored in ExhaustiveBaseline.
    """
    __tablename__ = "foss_projects"

    id:           Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    slug:         Mapped[str] = mapped_column(String(100), unique=True, nullable=False)  # e.g. "commons-lang"
    name:         Mapped[str] = mapped_column(String(200), nullable=False)
    description:  Mapped[str] = mapped_column(Text, nullable=False)
    language:     Mapped[str] = mapped_column(String(20), nullable=False)   # java | javascript
    domain:       Mapped[str] = mapped_column(String(100), nullable=False)  # utility | data-processing | etc.
    github_url:   Mapped[str] = mapped_column(String(500), nullable=False)
    license:      Mapped[str] = mapped_column(String(50), nullable=False)   # MIT | Apache-2.0 | etc.
    loc:          Mapped[int] = mapped_column(Integer, nullable=False)
    size_band:    Mapped[str] = mapped_column(String(20), nullable=False)   # small | medium | large
    test_count:   Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    version:      Mapped[str] = mapped_column(String(50), nullable=False)   # pinned version used
    zip_path:     Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # path on server
    is_active:    Mapped[bool] = mapped_column(Boolean, default=True)
    created_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    baseline: Mapped[Optional["ExhaustiveBaseline"]] = relationship(
        "ExhaustiveBaseline", back_populates="project", uselist=False
    )


class ExhaustiveBaseline(Base):
    """Pre-computed exhaustive mutation testing results for a FOSS project.
    Once computed, stored permanently as ground truth for all future sessions.
    source: 'computed' (ran on our server) | 'literature' (from published research)
    """
    __tablename__ = "exhaustive_baselines"

    id:              Mapped[str]   = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id:      Mapped[str]   = mapped_column(String(36), ForeignKey("foss_projects.id", ondelete="CASCADE"), nullable=False, unique=True)
    total_mutants:   Mapped[int]   = mapped_column(Integer, nullable=False)
    killed_mutants:  Mapped[int]   = mapped_column(Integer, nullable=False)
    mutation_score:  Mapped[float] = mapped_column(Float, nullable=False)     # 0.0–1.0
    execution_time_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    equivalent_mutants: Mapped[int] = mapped_column(Integer, default=0)
    operator_breakdown: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON {op: {total, killed}}
    source:          Mapped[str]   = mapped_column(String(20), default="computed")  # computed | literature
    computed_at:     Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    notes:           Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    project: Mapped["FossProject"] = relationship("FossProject", back_populates="baseline")
