"""
api/routers/jobs.py
Mutation testing job lifecycle.
"""
from __future__ import annotations

import asyncio
import logging
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user
from api.schemas import JobCreate, JobResultOut, JobStatusOut, MutantOut
from db.database import get_db, AsyncSessionLocal
from db.models.orm_models import User
from db.repositories import JobRepository, ProjectRepository

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/jobs", tags=["jobs"])


# ── Background job runner ─────────────────────────────────────────────────────
# Opens its OWN database session — completely independent of the request session.
# This is critical: the request session is closed the moment the HTTP response
# is sent, so any background task that reuses it will see a closed connection.

async def _dispatch_job(job_id: str, config: dict) -> None:
    from worker.celery_app import CELERY_AVAILABLE
    from worker.tasks import run_mutation_job, run_mutation_job_sync

    async with AsyncSessionLocal() as db:
        repo = JobRepository(db)
        celery_ok = False

        if CELERY_AVAILABLE and run_mutation_job is not None:
            try:
                task = run_mutation_job.delay(job_id, config)
                await repo.mark_running(job_id, task.id)
                await db.commit()
                log.info("Dispatched job %s to Celery (task=%s)", job_id, task.id)
                celery_ok = True
            except Exception as exc:
                log.warning("Celery dispatch failed (%s), falling back to sync", exc)

        if not celery_ok:
            await repo.mark_running(job_id, "sync")
            await db.commit()
            log.info("Running job %s synchronously (no Redis/Celery)", job_id)
            try:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None, run_mutation_job_sync, job_id, config
                )
                mutant_records = result.pop("mutant_records", [])

                # Re-open session for write (executor runs in a thread)
                async with AsyncSessionLocal() as write_db:
                    write_repo = JobRepository(write_db)
                    await write_repo.mark_completed(job_id, result)
                    await write_repo.save_mutant_records(job_id, mutant_records)
                    await write_db.commit()

                log.info("Job %s completed. score=%.1f%%",
                         job_id, result.get("mutation_score", 0) * 100)

            except Exception as exc:
                log.error("Sync job %s failed: %s", job_id, exc, exc_info=True)
                async with AsyncSessionLocal() as err_db:
                    err_repo = JobRepository(err_db)
                    await err_repo.mark_failed(job_id, str(exc))
                    await err_db.commit()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", response_model=JobStatusOut, status_code=202)
async def submit_job(
    payload: JobCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    proj_repo = ProjectRepository(db)
    project   = await proj_repo.get_by_id(payload.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    job_repo = JobRepository(db)
    job = await job_repo.create(
        owner_id=current_user.id,
        project_id=payload.project_id,
        time_budget_seconds=payload.time_budget_seconds,
        optimizer_strategy=payload.optimizer_strategy,
        jaccard_threshold=payload.jaccard_threshold,
        factor_weights=payload.factor_weights,
    )
    await db.commit()

    config = {
        "project_id":          project.id,
        "project_name":        project.name,
        "framework":           project.framework,
        "upload_path":         project.upload_path,
        "loc":                 project.loc or 5000,
        "test_count":          project.test_count or 100,
        "time_budget_seconds": payload.time_budget_seconds,
        "optimizer_strategy":  payload.optimizer_strategy,
        "jaccard_threshold":   payload.jaccard_threshold,
        "factor_weights":      payload.factor_weights,
        "mutant_count":        max(20, min(200, (project.loc or 5000) // 50)),
        "use_docker":          True,
    }

    # Pass the job_id and config only — background task opens its own session
    background_tasks.add_task(_dispatch_job, job.id, config)
    return job


@router.get("", response_model=List[JobStatusOut])
async def list_jobs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = JobRepository(db)
    return await repo.get_user_jobs(current_user.id)


@router.get("/{job_id}", response_model=JobStatusOut)
async def get_job_status(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = JobRepository(db)
    job  = await repo.get_by_id(job_id)
    if not job or job.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_id}/result", response_model=JobResultOut)
async def get_job_result(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = JobRepository(db)
    job  = await repo.get_by_id(job_id)
    if not job or job.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "COMPLETED":
        raise HTTPException(status_code=400, detail="Job not yet completed")
    return await repo.get_mutant_records(job_id)


@router.get("/{job_id}/export/csv")
async def export_csv(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from fastapi.responses import StreamingResponse
    import csv, io
    repo = JobRepository(db)
    job  = await repo.get_by_id(job_id)
    if not job or job.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Job not found")
    records = await repo.get_mutant_records(job_id)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["mutant_hash","operator","file","line","status","priority_score","execution_time"])
    for r in records:
        writer.writerow([r.mutant_hash, r.operator, r.file, r.line,
                         r.status, r.priority_score, r.execution_time])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=results-{job_id[:8]}.csv"},
    )
