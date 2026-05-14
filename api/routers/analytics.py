"""api/routers/analytics.py — Analytics and comparison endpoints."""
from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user
from db.database import get_db
from db.models.orm_models import User
from db.repositories.repositories import JobRepository, TestSessionRepository

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/dashboard")
async def dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """FR041–FR043: Dashboard metrics for current user."""
    session_repo = TestSessionRepository(db)
    job_repo     = JobRepository(db)

    total_sessions = await session_repo.count_for_user(current_user.id)
    active_sessions = await session_repo.count_active(current_user.id)
    jobs = await job_repo.get_user_jobs(current_user.id)
    completed = [j for j in jobs if j.status == "COMPLETED"]

    total_time_saved_min = sum(
        (j.time_saved_pct / 100) * (j.time_budget_seconds / 60)
        for j in completed
    )
    hours_saved = int(total_time_saved_min // 60)
    minutes_saved = int(total_time_saved_min % 60)

    return {
        "total_sessions": total_sessions,
        "active_sessions": active_sessions,
        "completed_jobs": len(completed),
        "time_saved_hours": hours_saved,
        "time_saved_minutes": minutes_saved,
        "time_saved_display": f"{hours_saved}h {minutes_saved}m saved" if hours_saved else f"{minutes_saved}m saved",
    }


@router.get("/trend")
async def score_trend(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Score trend over last 14 completed jobs."""
    repo = JobRepository(db)
    jobs = await repo.get_user_jobs(current_user.id)
    completed = [j for j in jobs if j.status == "COMPLETED" and j.strategy == "impt"][-14:]
    return [
        {
            "date": j.completed_at.strftime("%b %d") if j.completed_at else "",
            "score": round(j.mutation_score * 100, 1),
        }
        for j in completed
    ]


@router.get("/compare/{session_id}")
async def compare_strategies(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """FR119–FR128: Compare IMPT vs Random strategies for a session."""
    session_repo = TestSessionRepository(db)
    session      = await session_repo.get_by_id(session_id)
    if not session or session.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    job_repo = JobRepository(db)
    jobs     = await job_repo.get_session_jobs(session_id)

    result = {}
    for job in jobs:
        if job.status != "COMPLETED":
            continue
        result[job.strategy] = {
            "strategy":              job.strategy,
            "mutation_score":        round(job.mutation_score * 100, 1),
            "execution_time_min":    round(job.execution_time_seconds / 60, 1),
            "time_saved_pct":        round(job.time_saved_pct, 1),
            "estimated_correlation": round(job.estimated_score, 2),
            "mutants_tested":        job.executed_mutants,
            "total_mutants":         job.total_mutants,
            "job_id":                job.id,
            "operator_stats":        {},  # populated from MutantRecord aggregation
        }

    if not result:
        raise HTTPException(status_code=404, detail="No completed jobs found for this session.")

    return result
