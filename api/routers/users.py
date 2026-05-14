"""api/routers/users.py — User profile and settings."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user, hash_password, verify_password
from api.schemas.schemas import (
    ChangePasswordRequest, MessageOut, ProfileUpdate,
    UserOut, UserStatsOut,
)
from db.database import get_db
from db.models.orm_models import User
from db.repositories.repositories import AuditLogRepository, UserRepository

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me/stats", response_model=UserStatsOut)
async def my_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo  = UserRepository(db)
    stats = await repo.get_stats(current_user.id)
    # FR041: Calculate total time saved (estimated as avg_time_saved × sessions × 20min avg)
    total_saved_minutes = stats["avg_time_saved"] / 100 * stats["total_jobs"] * 20
    return UserStatsOut(**stats, total_time_saved_minutes=total_saved_minutes)


@router.patch("/me", response_model=UserOut)
async def update_profile(
    payload: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """FR129, FR134: Update profile information."""
    repo = UserRepository(db)
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        return current_user
    updated = await repo.update(current_user, **updates)
    await db.commit()
    return updated


@router.post("/me/password", response_model=MessageOut)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """FR130: Change password (requires current password)."""
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=422, detail="Passwords do not match.")

    repo       = UserRepository(db)
    audit_repo = AuditLogRepository(db)
    await repo.update(current_user, hashed_password=hash_password(payload.new_password))

    ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
    await audit_repo.log(
        category="AUTH", action="password_changed",
        message="User changed password",
        user_id=current_user.id, ip_address=ip,
    )
    await db.commit()
    return MessageOut(message="Password changed successfully.")


@router.delete("/me", response_model=MessageOut)
async def delete_account(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """FR132, NFR074: Delete account and all associated data."""
    repo = UserRepository(db)
    await repo.delete(current_user)
    await db.commit()
    return MessageOut(message="Your account and all associated data have been permanently deleted.")
