"""
api/routers/users.py
User account management
========================
GET   /api/users/me/stats     — account statistics for profile page
PATCH /api/users/me           — update name, org, preferences
POST  /api/users/me/password  — change password
GET   /api/users              — list all users (admin only)
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user, hash_password, verify_password
from api.schemas import UserOut
from db.database import get_db
from db.models.orm_models import MutationJob, User

router = APIRouter(prefix="/api/users", tags=["users"])


class ProfilePatch(BaseModel):
    full_name: Optional[str] = None
    organization: Optional[str] = None
    theme: Optional[str] = None
    language: Optional[str] = None
    notify_completion: Optional[bool] = None
    notify_weekly: Optional[bool] = None
    notify_updates: Optional[bool] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


@router.get("/me/stats")
async def get_my_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(MutationJob).where(
            MutationJob.owner_id == current_user.id,
            MutationJob.status == "COMPLETED",
        )
    )
    jobs = result.scalars().all()

    framework_counts: dict = {}
    for j in jobs:
        pass  # would join project to get framework

    avg_score = round(
        sum(j.mutation_score for j in jobs) / len(jobs) * 100, 1
    ) if jobs else 0.0

    avg_corr = round(
        sum(j.estimated_score for j in jobs) / len(jobs), 3
    ) if jobs else 0.0

    total_saved_hours = round(
        sum(j.execution_time_seconds * j.time_saved_pct / 100 for j in jobs) / 3600, 1
    ) if jobs else 0.0

    projects = len({j.project_id for j in jobs})

    return {
        "tests_run": len(jobs),
        "avg_mutation_score": avg_score,
        "avg_correlation": avg_corr,
        "total_time_saved_hours": total_saved_hours,
        "projects_tested": projects,
        "favorite_framework": "PIT",   # simplified
        "member_since": current_user.created_at.isoformat(),
    }


@router.patch("/me", response_model=UserOut)
async def update_me(
    payload: ProfilePatch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    for field, value in payload.model_dump(exclude_unset=True).items():
        if hasattr(current_user, field):
            setattr(current_user, field, value)
    db.add(current_user)
    return current_user


@router.post("/me/password", status_code=200)
async def change_password(
    payload: PasswordChange,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=422, detail="New password must be at least 8 characters")
    current_user.hashed_password = hash_password(payload.new_password)
    db.add(current_user)
    return {"message": "Password updated successfully"}


@router.get("", response_model=List[UserOut])
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    result = await db.execute(select(User))
    return result.scalars().all()
