"""
api/routers/profiles.py
Saved Profiles endpoints
========================
GET    /api/profiles           — list current user's profiles
POST   /api/profiles           — create a new profile
GET    /api/profiles/{id}      — get one profile
PUT    /api/profiles/{id}      — update a profile
DELETE /api/profiles/{id}      — delete a profile
POST   /api/profiles/{id}/use  — load profile into a job config (increments usage counter)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user
from db.database import get_db
from db.models.orm_models import SavedProfile, User

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class ProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    icon: str = "🎯"
    is_default: bool = False
    is_public: bool = False
    time_budget_seconds: int = Field(default=1200, ge=60, le=3600)
    optimizer_strategy: str = "AUTO"
    jaccard_threshold: float = Field(default=0.90, ge=0.5, le=1.0)
    factor_weights: Optional[dict] = None
    enabled_operators: Optional[list] = None
    thread_count: int = Field(default=4, ge=1, le=16)
    description: Optional[str] = None


class ProfileUpdate(ProfileCreate):
    name: Optional[str] = None


class ProfileOut(BaseModel):
    id: str
    owner_id: str
    name: str
    icon: str
    is_default: bool
    is_public: bool
    time_budget_seconds: int
    optimizer_strategy: str
    jaccard_threshold: float
    factor_weights: Optional[dict]
    enabled_operators: Optional[list]
    thread_count: int
    description: Optional[str]
    times_used: int
    avg_score: float
    avg_time_seconds: float
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_owned(profile_id: str, owner_id: str, db: AsyncSession) -> SavedProfile:
    result = await db.execute(
        select(SavedProfile).where(
            SavedProfile.id == profile_id,
            SavedProfile.owner_id == owner_id,
        )
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=List[ProfileOut])
async def list_profiles(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(SavedProfile)
        .where(SavedProfile.owner_id == current_user.id)
        .order_by(SavedProfile.is_default.desc(), SavedProfile.created_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=ProfileOut, status_code=201)
async def create_profile(
    payload: ProfileCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # If new profile is default, clear other defaults first
    if payload.is_default:
        await db.execute(
            update(SavedProfile)
            .where(SavedProfile.owner_id == current_user.id)
            .values(is_default=False)
        )

    profile = SavedProfile(
        owner_id=current_user.id,
        **payload.model_dump(),
    )
    db.add(profile)
    await db.flush()
    return profile


@router.get("/{profile_id}", response_model=ProfileOut)
async def get_profile(
    profile_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _get_owned(profile_id, current_user.id, db)


@router.put("/{profile_id}", response_model=ProfileOut)
async def update_profile(
    profile_id: str,
    payload: ProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = await _get_owned(profile_id, current_user.id, db)

    if payload.is_default:
        await db.execute(
            update(SavedProfile)
            .where(SavedProfile.owner_id == current_user.id, SavedProfile.id != profile_id)
            .values(is_default=False)
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    profile.updated_at = datetime.now(timezone.utc)
    return profile


@router.delete("/{profile_id}", status_code=204)
async def delete_profile(
    profile_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = await _get_owned(profile_id, current_user.id, db)
    await db.delete(profile)


@router.post("/{profile_id}/use", response_model=ProfileOut)
async def use_profile(
    profile_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Increment usage counter and return the profile config for job submission."""
    profile = await _get_owned(profile_id, current_user.id, db)
    profile.times_used += 1
    profile.updated_at = datetime.now(timezone.utc)
    return profile
