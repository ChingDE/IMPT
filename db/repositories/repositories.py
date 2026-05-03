"""
db/repositories/repositories.py
Data-access layer. All DB interaction goes through these classes,
keeping routers free of raw SQLAlchemy queries.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.orm_models import MutantRecord, MutationJob, ProjectRecord, User


# ─────────────────────────────────────────────────────────────────────────────
# User
# ─────────────────────────────────────────────────────────────────────────────

class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, user_id: str) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def create(
        self,
        email: str,
        hashed_password: str,
        full_name: Optional[str] = None,
        role: str = "student",
        username: Optional[str] = None,
        must_change_password: bool = False,
    ) -> User:
        user = User(
            email=email,
            hashed_password=hashed_password,
            full_name=full_name,
            role=role,
            username=username,
            must_change_password=must_change_password,
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def list_all(self) -> List[User]:
        result = await self.db.execute(select(User))
        return list(result.scalars().all())


# ─────────────────────────────────────────────────────────────────────────────
# Project
# ─────────────────────────────────────────────────────────────────────────────

class ProjectRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, project_id: str) -> Optional[ProjectRecord]:
        result = await self.db.execute(
            select(ProjectRecord).where(ProjectRecord.id == project_id)
        )
        return result.scalar_one_or_none()

    async def get_user_projects(self, owner_id: str) -> List[ProjectRecord]:
        result = await self.db.execute(
            select(ProjectRecord).where(ProjectRecord.owner_id == owner_id)
        )
        return list(result.scalars().all())

    async def create(
        self,
        owner_id: str,
        name: str,
        framework: str,
        loc: int = 0,
        test_count: int = 0,
        upload_path: Optional[str] = None,
        is_foss: bool = False,
        description: Optional[str] = None,
    ) -> ProjectRecord:
        project = ProjectRecord(
            owner_id=owner_id,
            name=name,
            framework=framework,
            loc=loc,
            test_count=test_count,
            upload_path=upload_path,
            is_foss=is_foss,
            description=description,
        )
        self.db.add(project)
        await self.db.flush()
        return project

    async def delete(self, project_id: str) -> bool:
        project = await self.get_by_id(project_id)
        if not project:
            return False
        await self.db.delete(project)
        return True


# ─────────────────────────────────────────────────────────────────────────────
# Mutation Job
# ─────────────────────────────────────────────────────────────────────────────

class JobRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, job_id: str) -> Optional[MutationJob]:
        result = await self.db.execute(
            select(MutationJob).where(MutationJob.id == job_id)
        )
        return result.scalar_one_or_none()

    async def get_user_jobs(
        self, owner_id: str, limit: int = 20
    ) -> List[MutationJob]:
        result = await self.db.execute(
            select(MutationJob)
            .where(MutationJob.owner_id == owner_id)
            .order_by(MutationJob.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_project_jobs(self, project_id: str) -> List[MutationJob]:
        result = await self.db.execute(
            select(MutationJob)
            .where(MutationJob.project_id == project_id)
            .order_by(MutationJob.created_at.desc())
        )
        return list(result.scalars().all())

    async def create(
        self,
        owner_id: str,
        project_id: str,
        time_budget_seconds: int,
        optimizer_strategy: str = "AUTO",
        jaccard_threshold: float = 0.90,
        factor_weights: Optional[dict] = None,
    ) -> MutationJob:
        job = MutationJob(
            owner_id=owner_id,
            project_id=project_id,
            time_budget_seconds=time_budget_seconds,
            optimizer_strategy=optimizer_strategy,
            jaccard_threshold=jaccard_threshold,
            factor_weights=factor_weights,
        )
        self.db.add(job)
        await self.db.flush()
        return job

    async def mark_running(self, job_id: str, celery_task_id: str) -> None:
        await self.db.execute(
            update(MutationJob)
            .where(MutationJob.id == job_id)
            .values(
                status="RUNNING",
                celery_task_id=celery_task_id,
                started_at=datetime.now(timezone.utc),
            )
        )

    async def mark_completed(self, job_id: str, result_data: dict) -> None:
        await self.db.execute(
            update(MutationJob)
            .where(MutationJob.id == job_id)
            .values(
                status="COMPLETED",
                completed_at=datetime.now(timezone.utc),
                **{k: v for k, v in result_data.items()},
            )
        )

    async def mark_failed(self, job_id: str, error: str) -> None:
        await self.db.execute(
            update(MutationJob)
            .where(MutationJob.id == job_id)
            .values(
                status="FAILED",
                completed_at=datetime.now(timezone.utc),
                error_message=error[:2000],
            )
        )

    async def save_mutant_records(
        self, job_id: str, records: list[dict]
    ) -> None:
        for r in records:
            self.db.add(MutantRecord(job_id=job_id, **r))
        await self.db.flush()

    async def get_mutant_records(self, job_id: str) -> List[MutantRecord]:
        result = await self.db.execute(
            select(MutantRecord).where(MutantRecord.job_id == job_id)
        )
        return list(result.scalars().all())
