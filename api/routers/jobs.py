"""api/routers/jobs.py — Job status, results, export."""
from __future__ import annotations

import json
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user
from api.schemas.schemas import JobResultOut, JobStatusOut, MutantOut
from db.database import get_db
from db.models.orm_models import User
from db.repositories.repositories import JobRepository, TestSessionRepository

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobStatusOut)
async def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = JobRepository(db)
    job  = await repo.get_by_id(job_id)
    if not job or job.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_id}/result", response_model=JobResultOut)
async def get_job_result(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = JobRepository(db)
    job  = await repo.get_by_id(job_id)
    if not job or job.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in ("PENDING", "RUNNING"):
        raise HTTPException(status_code=202, detail=f"Job is still {job.status.lower()}")
    if job.status == "FAILED":
        raise HTTPException(status_code=500, detail=f"Job failed: {job.error_message}")
    return job


@router.get("/{job_id}/mutants", response_model=List[MutantOut])
async def get_job_mutants(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = JobRepository(db)
    job  = await repo.get_by_id(job_id)
    if not job or job.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Job not found")
    return await repo.get_mutant_records(job_id)


@router.get("/{job_id}/export/csv")
async def export_csv(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """FR114: Export results as CSV."""
    import io, csv
    repo    = JobRepository(db)
    job     = await repo.get_by_id(job_id)
    if not job or job.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Job not found")
    records = await repo.get_mutant_records(job_id)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Mutant ID","Operator","File","Line","Status","Priority Score","Execution Time (s)","Killing Test","Original Code","Mutated Code","Explanation"])
    for r in records:
        writer.writerow([r.mutant_hash, r.operator, r.file, r.line,
                         r.status, f"{r.priority_score:.2f}", f"{r.execution_time:.2f}",
                         r.killing_test or "", r.original_code or "", r.mutated_code or "",
                         r.explanation or ""])
    buf.seek(0)

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=results-{job_id[:8]}.csv"},
    )
