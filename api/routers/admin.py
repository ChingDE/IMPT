"""
api/routers/admin.py
Admin-only endpoints.

FR135–FR138  Admin dashboard
FR139–FR146  User management
FR147–FR152  System configuration
FR153–FR158  Logs and monitoring
"""
from __future__ import annotations

import json
import io
import csv
import platform
import shutil
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_admin
from api.schemas.schemas import (
    AdminStatsOut, AdminUserOut, AuditLogOut,
    MessageOut, SystemConfigOut, SystemConfigUpdate,
)
from db.database import get_db
from db.models.orm_models import User
from db.repositories.repositories import (
    AuditLogRepository, JobRepository, SystemConfigRepository,
    TestSessionRepository, UserRepository,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ── Dashboard stats ────────────────────────────────────────────────────────────

@router.get("/stats", response_model=AdminStatsOut)
async def admin_stats(
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """FR136: System-wide statistics."""
    user_repo    = UserRepository(db)
    session_repo = TestSessionRepository(db)
    job_repo     = JobRepository(db)

    # Active users in last 7 days
    from sqlalchemy import select, func
    from db.models.orm_models import User as U
    cutoff = datetime.utcnow() - timedelta(days=7)
    r = await db.execute(
        select(func.count(U.id)).where(U.last_active_at >= cutoff)
    )
    active_7d = r.scalar_one()

    return AdminStatsOut(
        total_users=await user_repo.count(),
        total_sessions=len(await session_repo.all_paginated(limit=999999)),
        total_jobs=await job_repo.count_all(),
        completed_jobs=await job_repo.count_completed(),
        active_users_7d=active_7d,
    )


@router.get("/health-metrics")
async def health_metrics(current_admin: User = Depends(get_current_admin)):
    """FR158 / NFR036: Server health metrics with critical alert on disk > 90%."""
    try:
        import psutil
        cpu    = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk   = shutil.disk_usage("/")
        disk_pct = round(disk.used / disk.total * 100, 1)

        # NFR036: alert admin if disk > 90%
        if disk_pct > 90:
            try:
                from services.email import send_admin_error_alert
                send_admin_error_alert(
                    "Disk Space Critical",
                    f"Server disk usage is at {disk_pct}% — immediate action required.",
                    f"Used: {round(disk.used/(1024**3),1)} GB / Total: {round(disk.total/(1024**3),1)} GB"
                )
            except Exception:
                pass  # Never break the health endpoint

        return {
            "cpu_pct":        cpu,
            "memory_pct":     memory.percent,
            "memory_used_gb": round(memory.used  / (1024**3), 2),
            "memory_total_gb":round(memory.total / (1024**3), 2),
            "disk_pct":       disk_pct,
            "disk_used_gb":   round(disk.used  / (1024**3), 2),
            "disk_total_gb":  round(disk.total / (1024**3), 2),
        }
    except ImportError:
        return {"error": "psutil not installed — install it for health metrics"}


# ── User management ────────────────────────────────────────────────────────────

@router.get("/users", response_model=List[AdminUserOut])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),   # verified | unverified | active | suspended
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """FR139–FR141: List all users with search and status filter."""
    from sqlalchemy import select, or_
    from db.models.orm_models import User as U
    q = select(U).order_by(U.created_at.desc())
    if search:
        pattern = f"%{search}%"
        q = q.where(or_(
            U.email.ilike(pattern),
            U.first_name.ilike(pattern),
            U.last_name.ilike(pattern),
            U.organization.ilike(pattern),
        ))
    if status == "verified":
        q = q.where(U.is_verified == True)
    elif status == "unverified":
        q = q.where(U.is_verified == False)
    elif status == "active":
        q = q.where(U.is_active == True)
    elif status == "suspended":
        q = q.where(U.is_active == False)
    q = q.offset(skip).limit(limit)
    r = await db.execute(q)
    return list(r.scalars().all())


@router.get("/users/{user_id}", response_model=AdminUserOut)
async def get_user(
    user_id: str,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """FR142: View detailed user info."""
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/users/{user_id}/verify-email", response_model=MessageOut)
async def admin_verify_email(
    user_id: str,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """FR143: Manually verify user email."""
    repo       = UserRepository(db)
    audit_repo = AuditLogRepository(db)
    user       = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await repo.update(user, is_verified=True)
    await audit_repo.log(
        category="ADMIN", action="manual_email_verify",
        message=f"Admin manually verified email for user: {user.email}",
        user_id=current_admin.id,
    )
    await db.commit()
    return MessageOut(message="Email verified manually by admin.")


@router.post("/users/{user_id}/suspend", response_model=MessageOut)
async def suspend_user(
    user_id: str,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """FR144: Suspend user account."""
    repo       = UserRepository(db)
    audit_repo = AuditLogRepository(db)
    user       = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == "admin":
        raise HTTPException(status_code=403, detail="Cannot suspend another admin.")

    await repo.update(user, is_active=False)
    await audit_repo.log(
        category="ADMIN", action="user_suspended",
        message=f"User suspended: {user.email}",
        user_id=current_admin.id,
    )
    await db.commit()
    return MessageOut(message="User account suspended.")


@router.post("/users/{user_id}/unsuspend", response_model=MessageOut)
async def unsuspend_user(
    user_id: str,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """FR144: Re-activate suspended user."""
    repo       = UserRepository(db)
    audit_repo = AuditLogRepository(db)
    user       = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await repo.update(user, is_active=True)
    await audit_repo.log(
        category="ADMIN", action="user_unsuspended",
        message=f"User unsuspended: {user.email}",
        user_id=current_admin.id,
    )
    await db.commit()
    return MessageOut(message="User account reactivated.")


@router.delete("/users/{user_id}", response_model=MessageOut)
async def delete_user(
    user_id: str,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """FR145: Delete user and all data."""
    repo       = UserRepository(db)
    audit_repo = AuditLogRepository(db)
    user       = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_admin.id:
        raise HTTPException(status_code=403, detail="Cannot delete your own account via admin panel.")

    email = user.email
    await audit_repo.log(
        category="ADMIN", action="user_deleted",
        message=f"Admin deleted user: {email}",
        user_id=current_admin.id,
        level="WARNING",
    )
    await db.commit()  # Log must persist even after user deletion
    await repo.delete(user)
    await db.commit()
    return MessageOut(message=f"User {email} and all associated data deleted.")


@router.get("/users/export/csv")
async def export_users_csv(current_admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    """FR146: Export user list as CSV."""
    repo  = UserRepository(db)
    users = await repo.list_all(limit=10000)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["ID","Email","First Name","Last Name","Organization","Role","Verified","Active","Created","Last Login"])
    for u in users:
        writer.writerow([u.id, u.email, u.first_name, u.last_name, u.organization or "",
                         u.role, u.is_verified, u.is_active,
                         u.created_at.isoformat(), u.last_login_at.isoformat() if u.last_login_at else ""])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=users.csv"},
    )


# ── System configuration ───────────────────────────────────────────────────────

@router.get("/config", response_model=List[SystemConfigOut])
async def get_config(
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """FR147: Get all system configuration."""
    repo = SystemConfigRepository(db)
    return await repo.get_all()


@router.put("/config/{key}", response_model=MessageOut)
async def update_config(
    key: str,
    payload: SystemConfigUpdate,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """FR152: Update system configuration with audit log."""
    config_repo = SystemConfigRepository(db)
    audit_repo  = AuditLogRepository(db)

    old_value = await config_repo.get(key)
    await config_repo.set(key, payload.value, updated_by=current_admin.id)
    await audit_repo.log(
        category="ADMIN", action="config_changed",
        message=f"Config '{key}' changed",
        user_id=current_admin.id,
        extra={"key": key, "old": old_value, "new": payload.value},
    )
    await db.commit()
    return MessageOut(message=f"Configuration '{key}' updated successfully.")


# ── Audit logs ─────────────────────────────────────────────────────────────────

@router.get("/logs", response_model=List[AuditLogOut])
async def get_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    level: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """FR153–FR155: Searchable, filterable audit log."""
    repo = AuditLogRepository(db)
    return await repo.list_recent(skip=skip, limit=limit, level=level, category=category, user_id=user_id)


@router.get("/logs/export/csv")
async def export_logs_csv(
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """FR157: Export logs as CSV."""
    repo = AuditLogRepository(db)
    logs = await repo.list_recent(limit=10000)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Timestamp","Level","Category","User ID","Action","Message","IP","Outcome"])
    for l in logs:
        writer.writerow([l.created_at.isoformat(), l.level, l.category,
                         l.user_id or "", l.action, l.message,
                         l.ip_address or "", l.outcome])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
    )


@router.get("/charts")
async def admin_charts(
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """FR138: Time-series data for admin charts."""
    from sqlalchemy import text
    from datetime import datetime, timedelta

    # Last 14 days of user registrations and sessions per day
    cutoff = datetime.utcnow() - timedelta(days=14)

    reg_rows = await db.execute(text("""
        SELECT DATE(created_at) as d, COUNT(*) as cnt
        FROM users
        WHERE created_at >= :cutoff
        GROUP BY DATE(created_at)
        ORDER BY d
    """), {"cutoff": cutoff})

    sess_rows = await db.execute(text("""
        SELECT DATE(created_at) as d, COUNT(*) as cnt
        FROM test_sessions
        WHERE created_at >= :cutoff
        GROUP BY DATE(created_at)
        ORDER BY d
    """), {"cutoff": cutoff})

    score_rows = await db.execute(text("""
        SELECT DATE(completed_at) as d, ROUND(AVG(mutation_score)::numeric * 100, 1) as avg_score
        FROM mutation_jobs
        WHERE completed_at >= :cutoff
          AND status = 'COMPLETED'
          AND strategy != 'exhaustive'
          AND mutation_score > 0
        GROUP BY DATE(completed_at)
        ORDER BY d
    """), {"cutoff": cutoff})

    # Build complete 14-day series (fill missing days with 0)
    days = [(datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(13, -1, -1)]
    reg_map   = {str(r[0]): r[1] for r in reg_rows.fetchall()}
    sess_map  = {str(r[0]): r[1] for r in sess_rows.fetchall()}
    score_map = {str(r[0]): float(r[1]) for r in score_rows.fetchall() if r[1] is not None}

    return {
        "days": days,
        "registrations": [reg_map.get(d, 0) for d in days],
        "sessions":      [sess_map.get(d, 0) for d in days],
        "avg_scores":    [score_map.get(d) for d in days],  # None = no data that day
    }


@router.get("/recent-activity")
async def recent_activity(
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """FR137: Recent activity feed (last 15 log entries)."""
    repo = AuditLogRepository(db)
    logs = await repo.list_recent(limit=15)
    return [
        {
            "id":         l.id,
            "created_at": l.created_at.isoformat(),
            "level":      l.level,
            "category":   l.category,
            "action":     l.action,
            "message":    l.message,
            "outcome":    l.outcome,
        }
        for l in logs
    ]
