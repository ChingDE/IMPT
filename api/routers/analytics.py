"""
api/routers/analytics.py
Analytics & reporting endpoints
================================
GET  /api/analytics/trend          — performance trend (mutation scores over time)
GET  /api/analytics/compare        — compare two jobs side-by-side
GET  /api/analytics/summary        — aggregate stats for current user
GET  /api/analytics/admin          — system-wide stats (admin only)
GET  /api/jobs/{id}/export/csv     — download mutant results as CSV
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user
from db.database import get_db
from db.models.orm_models import MutantRecord, MutationJob, User

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


# ── Performance trend ────────────────────────────────────────────────────────

@router.get("/trend")
async def get_trend(
    days: int = Query(default=30, ge=7, le=90),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return mutation scores and time-saved for each completed job (last N days)."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(MutationJob)
        .where(
            MutationJob.owner_id == current_user.id,
            MutationJob.status == "COMPLETED",
            MutationJob.completed_at >= since,
        )
        .order_by(MutationJob.completed_at.asc())
    )
    jobs = result.scalars().all()

    return {
        "days": days,
        "points": [
            {
                "date": j.completed_at.isoformat() if j.completed_at else None,
                "project": j.project.name if hasattr(j, "project") else j.project_id[:8],
                "mutation_score": round(j.mutation_score * 100, 1),
                "time_saved_pct": round(j.time_saved_pct, 1),
                "correlation": round(j.estimated_score, 3),
                "job_id": j.id,
            }
            for j in jobs
        ],
        "avg_score": round(
            sum(j.mutation_score for j in jobs) / len(jobs) * 100, 1
        ) if jobs else 0.0,
    }


# ── User summary ─────────────────────────────────────────────────────────────

@router.get("/summary")
async def get_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aggregate stats for the current user's dashboard cards."""
    result = await db.execute(
        select(MutationJob).where(
            MutationJob.owner_id == current_user.id,
            MutationJob.status == "COMPLETED",
        )
    )
    jobs = result.scalars().all()

    if not jobs:
        return {
            "total_jobs": 0,
            "avg_mutation_score": 0.0,
            "avg_time_saved_pct": 0.0,
            "avg_correlation": 0.0,
            "total_time_saved_minutes": 0.0,
            "projects_tested": 0,
        }

    project_ids = {j.project_id for j in jobs}
    return {
        "total_jobs": len(jobs),
        "avg_mutation_score": round(sum(j.mutation_score for j in jobs) / len(jobs) * 100, 1),
        "avg_time_saved_pct": round(sum(j.time_saved_pct for j in jobs) / len(jobs), 1),
        "avg_correlation": round(sum(j.estimated_score for j in jobs) / len(jobs), 3),
        "total_time_saved_minutes": round(
            sum(j.execution_time_seconds * j.time_saved_pct / 100 for j in jobs) / 60, 1
        ),
        "projects_tested": len(project_ids),
    }


# ── Compare two jobs ─────────────────────────────────────────────────────────

@router.get("/compare")
async def compare_jobs(
    job_a: str = Query(..., description="First job ID"),
    job_b: str = Query(..., description="Second job ID (baseline)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Compare two completed jobs side by side."""
    async def _get_job(job_id: str) -> MutationJob:
        result = await db.execute(
            select(MutationJob).where(
                MutationJob.id == job_id,
                MutationJob.owner_id == current_user.id,
                MutationJob.status == "COMPLETED",
            )
        )
        j = result.scalar_one_or_none()
        if not j:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found or not completed")
        return j

    a = await _get_job(job_a)
    b = await _get_job(job_b)

    def _job_dict(j: MutationJob) -> dict:
        return {
            "id": j.id,
            "project_id": j.project_id,
            "mutation_score": round(j.mutation_score * 100, 1),
            "estimated_score": round(j.estimated_score * 100, 1),
            "ci_lower": round(j.ci_lower * 100, 1),
            "ci_upper": round(j.ci_upper * 100, 1),
            "time_saved_pct": round(j.time_saved_pct, 1),
            "execution_time_minutes": round(j.execution_time_seconds / 60, 1),
            "total_mutants": j.total_mutants,
            "selected_mutants": j.selected_mutants,
            "killed_mutants": j.killed_mutants,
            "subsumption_reduction_pct": round(j.subsumption_reduction_pct, 1),
            "optimizer_strategy": j.optimizer_strategy,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        }

    a_dict = _job_dict(a)
    b_dict = _job_dict(b)

    score_diff = a_dict["mutation_score"] - b_dict["mutation_score"]
    time_saved = b_dict["execution_time_minutes"] - a_dict["execution_time_minutes"]
    correlation = round(1 - abs(score_diff) / 100, 3) if b_dict["mutation_score"] > 0 else 0.0

    return {
        "session_a": a_dict,
        "session_b": b_dict,
        "diff": {
            "score_pct": round(score_diff, 1),
            "time_saved_minutes": round(time_saved, 1),
            "mutants_saved": b_dict["total_mutants"] - a_dict["selected_mutants"],
            "correlation": correlation,
            "effectiveness": "Similar" if abs(score_diff) <= 5 else "Different",
        },
        "recommendation": (
            "Use Session A configuration for daily development — good speed/quality tradeoff."
            if abs(score_diff) <= 5 else
            f"Session {'A' if score_diff > 0 else 'B'} achieves higher mutation score. "
            "Consider it for thorough analysis."
        ),
    }


# ── Admin stats ───────────────────────────────────────────────────────────────

@router.get("/admin")
async def get_admin_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    # Total users
    u_result = await db.execute(select(func.count(User.id)))
    total_users = u_result.scalar() or 0

    # Total jobs
    j_result = await db.execute(select(MutationJob))
    all_jobs = j_result.scalars().all()
    completed = [j for j in all_jobs if j.status == "COMPLETED"]

    # Today's active users (jobs created today)
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
    today_jobs = [j for j in all_jobs if j.created_at and j.created_at >= today]
    active_today = len({j.owner_id for j in today_jobs})

    return {
        "total_users": total_users,
        "total_jobs": len(all_jobs),
        "active_today": active_today,
        "completed_jobs": len(completed),
        "failed_jobs": sum(1 for j in all_jobs if j.status == "FAILED"),
        "avg_mutation_score": round(
            sum(j.mutation_score for j in completed) / len(completed) * 100, 1
        ) if completed else 0.0,
        "avg_time_saved": round(
            sum(j.time_saved_pct for j in completed) / len(completed), 1
        ) if completed else 0.0,
        "strategy_breakdown": _strategy_breakdown(completed),
    }


def _strategy_breakdown(jobs: list) -> dict:
    breakdown: dict = {}
    for j in jobs:
        s = j.optimizer_strategy
        if s not in breakdown:
            breakdown[s] = {"count": 0, "avg_score": 0.0, "avg_savings": 0.0}
        breakdown[s]["count"] += 1
        breakdown[s]["avg_score"] += j.mutation_score * 100
        breakdown[s]["avg_savings"] += j.time_saved_pct
    for s in breakdown:
        n = breakdown[s]["count"]
        breakdown[s]["avg_score"] = round(breakdown[s]["avg_score"] / n, 1)
        breakdown[s]["avg_savings"] = round(breakdown[s]["avg_savings"] / n, 1)
    return breakdown


# ── CSV export ───────────────────────────────────────────────────────────────

@router.get("/jobs/{job_id}/export/csv")
async def export_job_csv(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job_result = await db.execute(
        select(MutationJob).where(
            MutationJob.id == job_id,
            MutationJob.owner_id == current_user.id,
        )
    )
    job = job_result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    mutant_result = await db.execute(
        select(MutantRecord).where(MutantRecord.job_id == job_id)
    )
    mutants = mutant_result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Operator", "File", "Line", "Status",
        "Priority Score", "Execution Time (s)", "Original Code", "Mutated Code"
    ])
    for m in mutants:
        writer.writerow([
            m.mutant_hash, m.operator, m.file, m.line, m.status,
            m.priority_score, m.execution_time,
            m.original_code[:100], m.mutated_code[:100],
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=impt_job_{job_id[:8]}.csv"},
    )
