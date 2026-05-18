"""
db/repositories/repositories.py
Repository layer — no raw SQL anywhere else.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Optional, List

from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.orm_models import (
    User, EmailVerificationToken, PasswordResetToken,
    TestSession, MutationJob, MutantRecord, SavedProfile,
    AuditLog, SystemConfig
)


# ── UserRepository ─────────────────────────────────────────────────────────────

class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, user_id: str) -> Optional[User]:
        r = await self.db.execute(select(User).where(User.id == user_id))
        return r.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        r = await self.db.execute(select(User).where(User.email == email))
        return r.scalar_one_or_none()

    async def get_by_username(self, username: str) -> Optional[User]:
        r = await self.db.execute(select(User).where(User.username == username))
        return r.scalar_one_or_none()

    async def create(
        self,
        email: str,
        hashed_password: str,
        first_name: str = "",
        last_name: str = "",
        organization: Optional[str] = None,
        role: str = "user",
        username: Optional[str] = None,
        must_change_password: bool = False,
        is_verified: bool = False,
    ) -> User:
        user = User(
            email=email,
            hashed_password=hashed_password,
            first_name=first_name,
            last_name=last_name,
            organization=organization,
            role=role,
            username=username,
            must_change_password=must_change_password,
            is_verified=is_verified,
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def update(self, user: User, **kwargs) -> User:
        for k, v in kwargs.items():
            setattr(user, k, v)
        self.db.add(user)
        await self.db.flush()
        return user

    async def increment_failed_login(self, user: User) -> User:
        from config.settings import get_settings
        s = get_settings()
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= s.LOGIN_MAX_ATTEMPTS:
            user.lockout_until = datetime.utcnow() + timedelta(minutes=s.LOGIN_LOCKOUT_MINUTES)
        self.db.add(user)
        await self.db.flush()
        return user

    async def reset_failed_login(self, user: User) -> User:
        user.failed_login_attempts = 0
        user.lockout_until = None
        user.last_login_at = datetime.utcnow()
        user.last_active_at = datetime.utcnow()
        self.db.add(user)
        await self.db.flush()
        return user

    async def list_all(self, skip: int = 0, limit: int = 50) -> List[User]:
        r = await self.db.execute(
            select(User).order_by(User.created_at.desc()).offset(skip).limit(limit)
        )
        return list(r.scalars().all())

    async def count(self) -> int:
        r = await self.db.execute(select(func.count(User.id)))
        return r.scalar_one()

    async def delete(self, user: User) -> None:
        await self.db.delete(user)
        await self.db.flush()

    async def get_stats(self, user_id: str) -> dict:
        """Returns user-level aggregate stats."""
        sessions_r = await self.db.execute(
            select(func.count(TestSession.id)).where(TestSession.owner_id == user_id)
        )
        total_sessions = sessions_r.scalar_one()

        jobs_r = await self.db.execute(
            select(
                func.count(MutationJob.id),
                func.avg(MutationJob.mutation_score),
                func.avg(MutationJob.time_saved_pct),
                func.avg(MutationJob.estimated_score),
            ).where(
                MutationJob.owner_id == user_id,
                MutationJob.status == "COMPLETED",
            )
        )
        row = jobs_r.one()
        return {
            "total_sessions": total_sessions,
            "total_jobs": row[0] or 0,
            "avg_mutation_score": float(row[1] or 0),
            "avg_time_saved": float(row[2] or 0),
            "avg_correlation": float(row[3] or 0),
        }


# ── EmailVerificationRepository ────────────────────────────────────────────────

class EmailVerificationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, user_id: str, token: str, expires_at: datetime) -> EmailVerificationToken:
        t = EmailVerificationToken(user_id=user_id, token=token, expires_at=expires_at)
        self.db.add(t)
        await self.db.flush()
        return t

    async def get_by_token(self, token: str) -> Optional[EmailVerificationToken]:
        r = await self.db.execute(
            select(EmailVerificationToken).where(EmailVerificationToken.token == token)
        )
        return r.scalar_one_or_none()

    async def get_latest_for_user(self, user_id: str) -> Optional[EmailVerificationToken]:
        r = await self.db.execute(
            select(EmailVerificationToken)
            .where(EmailVerificationToken.user_id == user_id)
            .order_by(EmailVerificationToken.created_at.desc())
            .limit(1)
        )
        return r.scalar_one_or_none()

    async def invalidate_existing(self, user_id: str) -> None:
        await self.db.execute(
            update(EmailVerificationToken)
            .where(EmailVerificationToken.user_id == user_id, EmailVerificationToken.used == False)
            .values(used=True)
        )

    async def mark_used(self, token_obj: EmailVerificationToken) -> None:
        token_obj.used = True
        self.db.add(token_obj)
        await self.db.flush()


# ── PasswordResetRepository ────────────────────────────────────────────────────

class PasswordResetRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, user_id: str, token: str, expires_at: datetime) -> PasswordResetToken:
        # Invalidate any existing tokens first
        await self.db.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.user_id == user_id, PasswordResetToken.used == False)
            .values(used=True)
        )
        t = PasswordResetToken(user_id=user_id, token=token, expires_at=expires_at)
        self.db.add(t)
        await self.db.flush()
        return t

    async def get_by_token(self, token: str) -> Optional[PasswordResetToken]:
        r = await self.db.execute(
            select(PasswordResetToken).where(PasswordResetToken.token == token)
        )
        return r.scalar_one_or_none()

    async def mark_used(self, token_obj: PasswordResetToken) -> None:
        token_obj.used = True
        self.db.add(token_obj)
        await self.db.flush()


# ── TestSessionRepository ──────────────────────────────────────────────────────

class TestSessionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        owner_id: str,
        name: str,
        language: str,
        description: Optional[str] = None,
        foss_project_id: Optional[str] = None,
    ) -> TestSession:
        s = TestSession(
            owner_id=owner_id,
            name=name,
            language=language,
            description=description,
            foss_project_id=foss_project_id,
            status="not_started",
        )
        self.db.add(s)
        await self.db.flush()
        return s

    async def get_by_id(self, session_id: str) -> Optional[TestSession]:
        r = await self.db.execute(
            select(TestSession).where(TestSession.id == session_id)
        )
        return r.scalar_one_or_none()

    async def get_by_share_token(self, token: str) -> Optional[TestSession]:
        r = await self.db.execute(
            select(TestSession).where(TestSession.share_token == token)
        )
        return r.scalar_one_or_none()

    async def get_user_sessions(self, owner_id: str) -> List[TestSession]:
        r = await self.db.execute(
            select(TestSession)
            .where(TestSession.owner_id == owner_id)
            .order_by(TestSession.updated_at.desc())
        )
        return list(r.scalars().all())

    async def update(self, session: TestSession, **kwargs) -> TestSession:
        for k, v in kwargs.items():
            setattr(session, k, v)
        self.db.add(session)
        await self.db.flush()
        return session

    async def delete(self, session: TestSession) -> None:
        await self.db.delete(session)
        await self.db.flush()

    async def count_for_user(self, owner_id: str) -> int:
        r = await self.db.execute(
            select(func.count(TestSession.id)).where(TestSession.owner_id == owner_id)
        )
        return r.scalar_one()

    async def count_active(self, owner_id: str) -> int:
        r = await self.db.execute(
            select(func.count(TestSession.id)).where(
                TestSession.owner_id == owner_id,
                TestSession.status.in_(["not_started", "uploaded", "configured", "ready", "running"])
            )
        )
        return r.scalar_one()

    async def all_paginated(self, skip: int = 0, limit: int = 50) -> List[TestSession]:
        r = await self.db.execute(
            select(TestSession).order_by(TestSession.created_at.desc()).offset(skip).limit(limit)
        )
        return list(r.scalars().all())


# ── JobRepository ──────────────────────────────────────────────────────────────

class JobRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, session_id: str, owner_id: str, strategy: str = "impt", **kwargs) -> MutationJob:
        job = MutationJob(session_id=session_id, owner_id=owner_id, strategy=strategy, **kwargs)
        self.db.add(job)
        await self.db.flush()
        return job

    async def get_by_id(self, job_id: str) -> Optional[MutationJob]:
        r = await self.db.execute(select(MutationJob).where(MutationJob.id == job_id))
        return r.scalar_one_or_none()

    async def get_session_jobs(self, session_id: str) -> List[MutationJob]:
        r = await self.db.execute(
            select(MutationJob)
            .where(MutationJob.session_id == session_id)
            .order_by(MutationJob.created_at)
        )
        return list(r.scalars().all())

    async def get_user_jobs(self, owner_id: str) -> List[MutationJob]:
        r = await self.db.execute(
            select(MutationJob)
            .where(MutationJob.owner_id == owner_id)
            .order_by(MutationJob.created_at.desc())
        )
        return list(r.scalars().all())

    async def mark_running(self, job_id: str, task_id: str) -> None:
        await self.db.execute(
            update(MutationJob).where(MutationJob.id == job_id)
            .values(status="RUNNING", celery_task_id=task_id, started_at=datetime.utcnow())
        )

    async def mark_completed(self, job_id: str, result: dict) -> None:
        await self.db.execute(
            update(MutationJob).where(MutationJob.id == job_id).values(
                status="COMPLETED",
                completed_at=datetime.utcnow(),
                total_mutants=result.get("total_mutants", 0),
                selected_mutants=result.get("selected_mutants", 0),
                executed_mutants=result.get("executed_mutants", 0),
                killed_mutants=result.get("killed_mutants", 0),
                mutation_score=result.get("mutation_score", 0.0),
                estimated_score=result.get("estimated_score", 0.0),
                ci_lower=result.get("ci_lower", 0.0),
                ci_upper=result.get("ci_upper", 0.0),
                time_saved_pct=result.get("time_saved_pct", 0.0),
                subsumption_reduction_pct=result.get("subsumption_reduction_pct", 0.0),
                execution_time_seconds=result.get("execution_time_seconds", 0.0),
                result_json=json.dumps(result.get("result_json", {})),
            )
        )

    async def mark_failed(self, job_id: str, error: str) -> None:
        await self.db.execute(
            update(MutationJob).where(MutationJob.id == job_id)
            .values(status="FAILED", error_message=error, completed_at=datetime.utcnow())
        )

    async def save_mutant_records(self, job_id: str, records: list) -> None:
        for r in records:
            mr = MutantRecord(job_id=job_id, **r)
            self.db.add(mr)
        await self.db.flush()

    async def get_mutant_records(self, job_id: str) -> List[MutantRecord]:
        r = await self.db.execute(
            select(MutantRecord)
            .where(MutantRecord.job_id == job_id)
            .order_by(MutantRecord.priority_score.desc())
        )
        return list(r.scalars().all())

    async def get_stuck_jobs(self, timeout_seconds: int) -> List[MutationJob]:
        cutoff = datetime.utcnow() - timedelta(seconds=timeout_seconds)
        r = await self.db.execute(
            select(MutationJob).where(
                MutationJob.status.in_(["PENDING", "RUNNING"]),
                MutationJob.created_at < cutoff,
            )
        )
        return list(r.scalars().all())

    async def count_all(self) -> int:
        r = await self.db.execute(select(func.count(MutationJob.id)))
        return r.scalar_one()

    async def count_completed(self) -> int:
        r = await self.db.execute(
            select(func.count(MutationJob.id)).where(MutationJob.status == "COMPLETED")
        )
        return r.scalar_one()


# ── AuditLogRepository ─────────────────────────────────────────────────────────

class AuditLogRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def log(
        self,
        category: str,
        action: str,
        message: str,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        level: str = "INFO",
        outcome: str = "success",
        extra: Optional[dict] = None,
    ) -> None:
        entry = AuditLog(
            user_id=user_id,
            level=level,
            category=category,
            action=action,
            message=message,
            ip_address=ip_address,
            outcome=outcome,
            extra=json.dumps(extra) if extra else None,
        )
        self.db.add(entry)
        await self.db.flush()

    async def list_recent(
        self,
        skip: int = 0,
        limit: int = 100,
        level: Optional[str] = None,
        category: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[AuditLog]:
        q = select(AuditLog).order_by(AuditLog.created_at.desc())
        if level:
            q = q.where(AuditLog.level == level)
        if category:
            q = q.where(AuditLog.category == category)
        if user_id:
            q = q.where(AuditLog.user_id == user_id)
        q = q.offset(skip).limit(limit)
        r = await self.db.execute(q)
        return list(r.scalars().all())

    async def count_errors_since(self, since: datetime) -> int:
        r = await self.db.execute(
            select(func.count(AuditLog.id)).where(
                AuditLog.level == "ERROR",
                AuditLog.created_at >= since,
            )
        )
        return r.scalar_one()


# ── SystemConfigRepository ─────────────────────────────────────────────────────

class SystemConfigRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, key: str, default: str = "") -> str:
        r = await self.db.execute(select(SystemConfig).where(SystemConfig.key == key))
        obj = r.scalar_one_or_none()
        return obj.value if obj else default

    async def set(self, key: str, value: str, updated_by: Optional[str] = None) -> None:
        r = await self.db.execute(select(SystemConfig).where(SystemConfig.key == key))
        obj = r.scalar_one_or_none()
        if obj:
            obj.value = value
            obj.updated_by = updated_by
            self.db.add(obj)
        else:
            self.db.add(SystemConfig(key=key, value=value, updated_by=updated_by))
        await self.db.flush()

    async def get_all(self) -> List[SystemConfig]:
        r = await self.db.execute(select(SystemConfig).order_by(SystemConfig.key))
        return list(r.scalars().all())
