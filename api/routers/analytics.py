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

    # Compute total time saved using actual timestamps
    total_saved_secs = 0.0
    for j in completed:
        if j.strategy == "exhaustive":
            continue  # skip exhaustive — it's the baseline not the saving
        if j.started_at and j.completed_at:
            actual_secs = (j.completed_at - j.started_at).total_seconds()
        else:
            actual_secs = j.execution_time_seconds or 0
        # Estimate exhaustive would have taken: actual × (total/selected)
        if actual_secs > 0 and (j.selected_mutants or 0) > 0 and (j.total_mutants or 0) > 0:
            est_exhaustive = actual_secs * (j.total_mutants / j.selected_mutants)
            total_saved_secs += max(0, est_exhaustive - actual_secs)

    hours_saved   = int(total_saved_secs // 3600)
    minutes_saved = int((total_saved_secs % 3600) // 60)
    seconds_saved = int(total_saved_secs % 60)

    if hours_saved:
        display = f"{hours_saved}h {minutes_saved}m saved"
    elif minutes_saved:
        display = f"{minutes_saved}m {seconds_saved}s saved"
    else:
        display = f"{seconds_saved}s saved" if seconds_saved else "—"

    return {
        "total_sessions": total_sessions,
        "active_sessions": active_sessions,
        "completed_jobs": len(completed),
        "time_saved_hours":   hours_saved,
        "time_saved_minutes": minutes_saved,
        "time_saved_seconds": seconds_saved,
        "time_saved_display": display,
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
    """FR119–FR128: Return all jobs for a session for comparison and results display."""
    session_repo = TestSessionRepository(db)
    session      = await session_repo.get_by_id(session_id)
    if not session or session.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    job_repo = JobRepository(db)
    jobs     = await job_repo.get_session_jobs(session_id)

    if not jobs:
        raise HTTPException(status_code=404, detail="No jobs found for this session.")

    # Find primary and exhaustive jobs
    primary_job    = next((j for j in jobs if j.strategy != "exhaustive"), None)
    exhaustive_job = next((j for j in jobs if j.strategy == "exhaustive"), None)

    # Compute real time-saved against exhaustive if both ran
    def _elapsed(job) -> float:
        if job is None:
            return 0.0
        try:
            if job.started_at and job.completed_at:
                delta = job.completed_at - job.started_at
                secs = delta.total_seconds()
                if secs > 0:
                    return secs
        except Exception:
            pass
        return float(job.execution_time_seconds or 0)

    primary_exec    = _elapsed(primary_job)
    exhaustive_exec = _elapsed(exhaustive_job)

    # If exhaustive didn't run (or ran but has 0 time), estimate it:
    # estimated_exhaustive = primary_time × (total / selected)
    # This reflects how long it would take to run ALL mutants at the same rate
    if exhaustive_exec == 0 and primary_job and (primary_job.selected_mutants or 0) > 0:
        ratio = (primary_job.total_mutants or 1) / (primary_job.selected_mutants or 1)
        estimated_exhaustive_exec = primary_exec * ratio
    else:
        estimated_exhaustive_exec = exhaustive_exec

    if primary_exec > 0 and estimated_exhaustive_exec > 0:
        real_time_saved = round((1 - primary_exec / estimated_exhaustive_exec) * 100, 1)
    elif primary_job and (primary_job.time_saved_pct or 0) > 0:
        real_time_saved = round(primary_job.time_saved_pct, 1)
    else:
        real_time_saved = 0.0

    # Compute real correlation if both completed
    primary_score    = (primary_job.mutation_score   or 0) if primary_job   else 0
    exhaustive_score = (exhaustive_job.mutation_score or 0) if exhaustive_job else 0
    if primary_score > 0 and exhaustive_score > 0:
        real_correlation = round(1 - abs(primary_score - exhaustive_score) / exhaustive_score, 3)
    else:
        real_correlation = None

    result = {}
    for job in jobs:
        is_primary    = job.strategy != "exhaustive"
        is_exhaustive = job.strategy == "exhaustive"

        # Compute real elapsed time from DB timestamps — most accurate source
        real_exec_secs = _elapsed(job)
        result[job.strategy] = {
            "id":                     job.id,
            "strategy":               job.strategy,
            "status":                 job.status,
            # Scores as fractions (0.0–1.0) — let frontend handle display
            "mutation_score":         job.mutation_score or 0,
            "estimated_score":        job.estimated_score or 0,
            "ci_lower":               job.ci_lower or 0,
            "ci_upper":               job.ci_upper or 0,
            # Timing
            # Timing — derived from DB timestamps, not stored estimate
            "execution_time_seconds":           real_exec_secs,
            "execution_time_min":               round(real_exec_secs / 60, 1),
            "estimated_exhaustive_seconds":     estimated_exhaustive_exec if is_primary else real_exec_secs,
            # Mutant counts
            "executed_mutants":       job.executed_mutants or 0,
            "selected_mutants":       job.selected_mutants or 0,
            "total_mutants":          job.total_mutants or 0,
            "killed_mutants":         job.killed_mutants or 0,
            # Comparison metrics (computed above using both jobs)
            "time_saved_pct":         real_time_saved if is_primary else 0,
            "real_correlation":       real_correlation if is_primary else None,
            # Legacy field name
            "estimated_correlation":  round(job.estimated_score or 0, 3),
            "operator_stats":         {},
        }

    return result
