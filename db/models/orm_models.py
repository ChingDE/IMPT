"""
db/models/orm_models.py
SQLAlchemy ORM table definitions.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey,
    Integer, String, Text, JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


# ─────────────────────────────────────────────────────────────────────────────
# Users
# ─────────────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[str]                = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str]             = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str]   = mapped_column(String(255), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[str]              = mapped_column(String(50), default="student")  # student | professional | admin
    is_active: Mapped[bool]        = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime]   = mapped_column(DateTime(timezone=True), default=_now)

    # Admin-specific fields
    username: Mapped[Optional[str]] = mapped_column(String(64), unique=True, index=True, nullable=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    projects: Mapped[list["ProjectRecord"]] = relationship(
        "ProjectRecord", back_populates="owner", cascade="all, delete-orphan"
    )
    jobs: Mapped[list["MutationJob"]] = relationship(
        "MutationJob", back_populates="owner", cascade="all, delete-orphan"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Projects
# ─────────────────────────────────────────────────────────────────────────────

class ProjectRecord(Base):
    __tablename__ = "projects"

    id: Mapped[str]        = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_id: Mapped[str]  = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    name: Mapped[str]      = mapped_column(String(255), nullable=False)
    framework: Mapped[str] = mapped_column(String(20), nullable=False)   # PIT | STRYKER
    upload_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    loc: Mapped[int]           = mapped_column(Integer, default=0)
    test_count: Mapped[int]    = mapped_column(Integer, default=0)
    is_foss: Mapped[bool]      = mapped_column(Boolean, default=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    owner: Mapped["User"] = relationship("User", back_populates="projects")
    jobs: Mapped[list["MutationJob"]] = relationship(
        "MutationJob", back_populates="project", cascade="all, delete-orphan"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Mutation Testing Jobs
# ─────────────────────────────────────────────────────────────────────────────

class MutationJob(Base):
    __tablename__ = "mutation_jobs"

    id: Mapped[str]          = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_id: Mapped[str]    = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    project_id: Mapped[str]  = mapped_column(String(36), ForeignKey("projects.id"), nullable=False)
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Configuration
    time_budget_seconds: Mapped[int]  = mapped_column(Integer, default=1800)
    optimizer_strategy: Mapped[str]   = mapped_column(String(20), default="AUTO")
    jaccard_threshold: Mapped[float]  = mapped_column(Float, default=0.90)
    factor_weights: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Status lifecycle: PENDING → RUNNING → COMPLETED | FAILED
    status: Mapped[str]    = mapped_column(String(20), default="PENDING", index=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timing
    created_at: Mapped[datetime]          = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[Optional[datetime]]  = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Results (written when job completes)
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

    # Full JSON result blob (for detailed report endpoint)
    result_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    owner: Mapped["User"] = relationship("User", back_populates="jobs")
    project: Mapped["ProjectRecord"] = relationship("ProjectRecord", back_populates="jobs")
    mutant_records: Mapped[list["MutantRecord"]] = relationship(
        "MutantRecord", back_populates="job", cascade="all, delete-orphan"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Per-mutant records (for detailed drilldown)
# ─────────────────────────────────────────────────────────────────────────────

class MutantRecord(Base):
    __tablename__ = "mutant_records"

    id: Mapped[str]      = mapped_column(String(36), primary_key=True, default=_uuid)
    job_id: Mapped[str]  = mapped_column(String(36), ForeignKey("mutation_jobs.id"), nullable=False)
    mutant_hash: Mapped[str] = mapped_column(String(16), nullable=False)

    operator: Mapped[str]       = mapped_column(String(30), nullable=False)
    file: Mapped[str]           = mapped_column(String(512), nullable=False)
    line: Mapped[int]           = mapped_column(Integer, nullable=False)
    original_code: Mapped[str]  = mapped_column(Text, nullable=False)
    mutated_code: Mapped[str]   = mapped_column(Text, nullable=False)
    status: Mapped[str]         = mapped_column(String(20), nullable=False)
    priority_score: Mapped[float]  = mapped_column(Float, default=0.0)
    execution_time: Mapped[float]  = mapped_column(Float, default=0.0)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    job: Mapped["MutationJob"] = relationship("MutationJob", back_populates="mutant_records")


# ─────────────────────────────────────────────────────────────────────────────
# Saved Profiles  (wireframe: Saved Profiles page)
# ─────────────────────────────────────────────────────────────────────────────

class SavedProfile(Base):
    __tablename__ = "saved_profiles"

    id: Mapped[str]       = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    name: Mapped[str]     = mapped_column(String(255), nullable=False)
    icon: Mapped[str]     = mapped_column(String(10), default="🎯")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_public: Mapped[bool]  = mapped_column(Boolean, default=False)

    # Configuration snapshot
    time_budget_seconds: Mapped[int]   = mapped_column(Integer, default=1200)
    optimizer_strategy: Mapped[str]    = mapped_column(String(20), default="AUTO")
    jaccard_threshold: Mapped[float]   = mapped_column(Float, default=0.90)
    factor_weights: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    enabled_operators: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    thread_count: Mapped[int]          = mapped_column(Integer, default=4)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Usage statistics
    times_used: Mapped[int]     = mapped_column(Integer, default=0)
    avg_score: Mapped[float]    = mapped_column(Float, default=0.0)
    avg_time_seconds: Mapped[float] = mapped_column(Float, default=0.0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    owner: Mapped["User"] = relationship("User", backref="saved_profiles")
