"""
api/routers/sessions.py
Test session lifecycle: Create → Upload → Configure Operators → Set Budget → Start.

FR051–FR057  Create new session
FR058–FR069  Project upload
FR070–FR079  Mutation operator configuration
FR080–FR090  Time budget configuration
FR091–FR096  Review and start
FR116        Shareable links
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import generate_secure_token, get_current_user
from api.schemas.schemas import (
    MessageOut, OperatorConfigRequest, SessionCreate,
    SessionOut, SessionUpdate, TimeBudgetRequest,
)
from config.settings import get_settings
from db.database import get_db
from db.models.orm_models import User
from db.repositories.repositories import AuditLogRepository, TestSessionRepository

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sessions", tags=["sessions"])
settings = get_settings()


def _ip(request: Request) -> str:
    return request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")


# ── Create session ─────────────────────────────────────────────────────────────

@router.post("", response_model=SessionOut, status_code=201)
async def create_session(
    payload: SessionCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """FR051–FR057: Create a named test session."""
    if not current_user.is_verified:
        raise HTTPException(status_code=403, detail="Please verify your email before creating sessions.")

    repo       = TestSessionRepository(db)
    audit_repo = AuditLogRepository(db)

    session = await repo.create(
        owner_id=current_user.id,
        name=payload.name,
        language=payload.language,
        description=payload.description,
        foss_project_id=payload.foss_project_id,
        weight_config=payload.weight_config,
    )

    await audit_repo.log(
        category="TESTING", action="session_created",
        message=f"Session created: {payload.name}",
        user_id=current_user.id, ip_address=_ip(request),
    )
    await db.commit()
    return session


# ── List sessions ──────────────────────────────────────────────────────────────

@router.get("", response_model=List[SessionOut])
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """FR044: List user's sessions sorted by last modified, with primary job metrics."""
    from db.repositories.repositories import JobRepository
    repo     = TestSessionRepository(db)
    job_repo = JobRepository(db)
    sessions = await repo.get_user_sessions(current_user.id)
    all_jobs = await job_repo.get_user_jobs(current_user.id)

    # Attach primary job metrics to each session
    job_map = {}
    for j in all_jobs:
        if j.strategy != "exhaustive" and j.status == "COMPLETED":
            if j.session_id not in job_map:
                job_map[j.session_id] = j

    result = []
    for s in sessions:
        job = job_map.get(s.id)
        d = s.__dict__.copy()
        d["mutation_score"]     = round((job.mutation_score or 0) * 100, 1) if job else None
        d["executed_mutants"]   = job.executed_mutants if job else None
        d["total_mutants"]      = job.total_mutants if job else None
        d["time_saved_pct"]     = round(job.time_saved_pct or 0, 1) if job else None
        result.append(d)
    return result


# ── Get session ────────────────────────────────────────────────────────────────

@router.get("/{session_id}", response_model=SessionOut)
async def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo    = TestSessionRepository(db)
    session = await repo.get_by_id(session_id)
    if not session or session.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


# ── Get session jobs ──────────────────────────────────────────────────────────

@router.get("/{session_id}/jobs")
async def get_session_jobs(
    session_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all jobs for a session with live progress metrics."""
    repo    = TestSessionRepository(db)
    session = await repo.get_by_id(session_id)
    if not session or session.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    from db.repositories.repositories import JobRepository
    job_repo = JobRepository(db)
    jobs     = await job_repo.get_session_jobs(session_id)
    return [
        {
            "id":              j.id,
            "strategy":        j.strategy,
            "status":          j.status,
            "total_mutants":   j.total_mutants,
            "selected_mutants":j.selected_mutants,
            "executed_mutants":j.executed_mutants,
            "killed_mutants":  j.killed_mutants,
            "mutation_score":  round(j.mutation_score * 100, 1),
            "time_saved_pct":  round(j.time_saved_pct, 1),
            "execution_time_seconds": j.execution_time_seconds,
            "error_message":   j.error_message,
        }
        for j in jobs
    ]


# ── Update session name/description ───────────────────────────────────────────

@router.patch("/{session_id}", response_model=SessionOut)
async def update_session(
    session_id: str,
    payload: SessionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo    = TestSessionRepository(db)
    session = await repo.get_by_id(session_id)
    if not session or session.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    updated = await repo.update(session, **updates)
    await db.commit()
    return updated


# ── Delete session ─────────────────────────────────────────────────────────────

@router.delete("/{session_id}", response_model=MessageOut)
async def delete_session(
    session_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """FR047: Delete session with all associated data."""
    repo       = TestSessionRepository(db)
    audit_repo = AuditLogRepository(db)
    session    = await repo.get_by_id(session_id)
    if not session or session.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    name = session.name

    # Remove uploaded files
    if session.upload_path and Path(session.upload_path).exists():
        shutil.rmtree(session.upload_path, ignore_errors=True)

    await repo.delete(session)

    await audit_repo.log(
        category="TESTING", action="session_deleted",
        message=f"Session deleted: {name}",
        user_id=current_user.id, ip_address=_ip(request),
    )
    await db.commit()
    return MessageOut(message="Session deleted successfully.")


# ── Upload project ─────────────────────────────────────────────────────────────

@router.post("/{session_id}/upload", response_model=SessionOut)
async def upload_project(
    session_id: str,
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """FR058–FR069: Upload project ZIP and validate structure."""
    repo    = TestSessionRepository(db)
    session = await repo.get_by_id(session_id)
    if not session or session.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    # FR059: Validate file type
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=415, detail="Invalid file type. Please upload a .zip file.")

    # Read and check size
    contents = await file.read()
    size_bytes = len(contents)
    if size_bytes > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File size exceeds {settings.MAX_UPLOAD_MB}MB limit.")

    # Create session-specific upload dir (FR066)
    upload_dir = Path(settings.UPLOAD_DIR) / current_user.id / session_id / "source"
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Clear any previous upload
    for f in upload_dir.iterdir():
        if f.is_file():
            f.unlink()
        elif f.is_dir():
            shutil.rmtree(f)

    # Extract ZIP with path traversal protection (NFR019)
    try:
        with zipfile.ZipFile(__import__("io").BytesIO(contents)) as zf:
            for member in zf.infolist():
                # Security: reject path traversal
                member_path = Path(member.filename)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise HTTPException(status_code=422, detail="Invalid file path in archive.")
            zf.extractall(upload_dir)
    except zipfile.BadZipFile:
        raise HTTPException(status_code=422, detail="The uploaded file is not a valid ZIP archive.")

    # Find project root — unwrap single top-level dir (handles GitHub zip format)
    items = list(upload_dir.iterdir())
    project_root = upload_dir
    if len(items) == 1 and items[0].is_dir():
        project_root = items[0]

    # Validate project structure (FR062, FR063, FR064)
    # Search recursively up to 2 levels to handle nested structures
    language = session.language
    if language == "java":
        has_build = (
            (project_root / "pom.xml").exists() or
            (project_root / "build.gradle").exists() or
            any(project_root.rglob("pom.xml")) or
            any(project_root.rglob("build.gradle"))
        )
        if not has_build:
            raise HTTPException(
                status_code=422,
                detail="Java build configuration file (pom.xml or build.gradle) not found in project."
            )
        # Find actual root with build file for accurate LOC counting
        for p in list(project_root.rglob("pom.xml")) + list(project_root.rglob("build.gradle")):
            project_root = p.parent
            break
        detected_framework = "PIT"
    else:
        # Search recursively for package.json (handles GitHub zip with subfolder)
        pkg_candidates = list(project_root.rglob("package.json"))
        # Filter out node_modules
        pkg_candidates = [p for p in pkg_candidates if "node_modules" not in str(p)]
        has_pkg = bool(pkg_candidates)
        if not has_pkg:
            raise HTTPException(
                status_code=422,
                detail="package.json not found in project. Please ensure this is a JavaScript/Node.js project."
            )
        # Use the shallowest package.json as project root
        pkg_candidates.sort(key=lambda p: len(p.parts))
        project_root = pkg_candidates[0].parent
        detected_framework = "Stryker"

    # Count files and LOC
    file_count = sum(1 for _ in project_root.rglob("*") if _.is_file())
    loc = _count_loc(project_root, language)
    test_count = _count_tests(project_root, language)

    # FR080 — Estimate mutant count (empirical: ~10-15 mutants per KLOC for Java, ~8-12 for JS)
    mutant_rate   = 12 if language == "java" else 10
    est_mutants   = max(10, int(loc / 1000 * mutant_rate))

    # FR081 — Recommend time budget based on project size
    # Rule: 1 min per 20 mutants, capped at 120 min, floor 5 min
    raw_rec       = max(5, min(120, int(est_mutants / 20)))
    rec_min       = max(5, raw_rec - 5)
    rec_max       = min(120, raw_rec + 10)

    updated = await repo.update(
        session,
        upload_path=str(project_root),
        upload_filename=file.filename,
        upload_size_bytes=size_bytes,
        file_count=file_count,
        loc=loc,
        test_count=test_count,
        detected_framework=detected_framework,
        estimated_mutant_count=est_mutants,
        recommended_budget_min=rec_min,
        recommended_budget_max=rec_max,
        status="uploaded",
    )
    await db.commit()
    return updated


def _count_loc(root: Path, language: str) -> int:
    ext = ".java" if language == "java" else ".js"
    total = 0
    for f in root.rglob(f"*{ext}"):
        try:
            lines = f.read_text(errors="ignore").splitlines()
            total += sum(1 for l in lines if l.strip() and not l.strip().startswith("//"))
        except Exception:
            pass
    return total


def _count_tests(root: Path, language: str) -> int:
    count = 0
    if language == "java":
        for f in root.rglob("*.java"):
            if "test" in f.name.lower() or "test" in str(f.parent).lower():
                try:
                    count += f.read_text(errors="ignore").count("@Test")
                except Exception:
                    pass
    else:
        for f in root.rglob("*.test.*"):
            count += 1
        for f in root.rglob("*.spec.*"):
            count += 1
    return count


# ── Configure mutation operators ───────────────────────────────────────────────

@router.post("/{session_id}/operators", response_model=SessionOut)
async def configure_operators(
    session_id: str,
    payload: OperatorConfigRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """FR070–FR079: Save operator selection to session."""
    repo    = TestSessionRepository(db)
    session = await repo.get_by_id(session_id)
    if not session or session.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    # FOSS sessions skip upload so status stays 'not_started' — allow that too
    if session.status not in ("not_started", "uploaded", "configured", "ready", "running", "completed", "failed"):
        raise HTTPException(status_code=400, detail="Project must be uploaded before configuring operators.")
    if not session.upload_path and not getattr(session, "foss_project_id", None):
        raise HTTPException(status_code=400, detail="Project must be uploaded or a FOSS project selected before configuring operators.")
    if not payload.selected_operators:
        raise HTTPException(status_code=422, detail="At least one mutation operator must be selected.")

    updated = await repo.update(
        session,
        selected_operators=json.dumps(payload.selected_operators),
        status="configured",
    )
    await db.commit()
    return updated


# ── Set time budget ────────────────────────────────────────────────────────────

@router.post("/{session_id}/budget", response_model=SessionOut)
async def set_budget(
    session_id: str,
    payload: TimeBudgetRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """FR080–FR090: Save time budget and comparison settings."""
    repo    = TestSessionRepository(db)
    session = await repo.get_by_id(session_id)
    if not session or session.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status not in ("configured", "ready", "running", "completed", "failed"):
        raise HTTPException(status_code=400, detail="Operators must be configured before setting time budget.")
    if not session.selected_operators:
        raise HTTPException(status_code=400, detail="Operators must be configured before setting time budget.")

    updated = await repo.update(
        session,
        time_budget_minutes=payload.time_budget_minutes,
        selected_strategy=payload.selected_strategy,
        run_exhaustive=payload.run_exhaustive,
        run_comparison=payload.run_comparison,
        run_operator_based=payload.run_operator_based,
        status="ready",
    )
    await db.commit()
    return updated


# ── Start testing ──────────────────────────────────────────────────────────────

@router.post("/{session_id}/start", status_code=202)
async def start_testing(
    session_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """FR094: Submit all mutation testing jobs for this session."""
    repo       = TestSessionRepository(db)
    audit_repo = AuditLogRepository(db)
    session    = await repo.get_by_id(session_id)

    if not session or session.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status not in ("ready", "configured"):
        raise HTTPException(status_code=400, detail="Session is not ready to start. Complete all configuration steps first.")
    if not session.upload_path and not getattr(session, "foss_project_id", None):
        raise HTTPException(status_code=400, detail="Please upload your project or select a FOSS project first.")
    if not session.selected_operators:
        raise HTTPException(status_code=400, detail="Please configure mutation operators first.")
    if not session.time_budget_minutes:
        raise HTTPException(status_code=400, detail="Please set a time budget first.")

    from db.repositories.repositories import JobRepository
    job_repo = JobRepository(db)

    operators      = json.loads(session.selected_operators or "[]")
    budget_seconds = (session.time_budget_minutes or 20) * 60
    strategy       = getattr(session, "selected_strategy", "impt") or "impt"
    run_exhaustive = getattr(session, "run_exhaustive", False)

    optimizer_map = {"impt": "AUTO", "random": "GREEDY", "operator_based": "GREEDY"}

    # Primary strategy job
    primary_job = await job_repo.create(
        session_id=session_id,
        owner_id=current_user.id,
        strategy=strategy,
        time_budget_seconds=budget_seconds,
        optimizer_strategy=optimizer_map.get(strategy, "AUTO"),
        jaccard_threshold=0.90,
        selected_operators=session.selected_operators,
    )

    # Optional exhaustive job — no knapsack, no time cap
    exhaustive_job = None
    if run_exhaustive:
        exhaustive_job = await job_repo.create(
            session_id=session_id,
            owner_id=current_user.id,
            strategy="exhaustive",
            time_budget_seconds=86400,
            optimizer_strategy="NONE",
            jaccard_threshold=0.90,
            selected_operators=session.selected_operators,
        )

    await repo.update(session, status="running", started_at=datetime.utcnow())

    await audit_repo.log(
        category="TESTING", action="session_started",
        message=f"Testing started: {session.name} | strategy={strategy} | exhaustive={run_exhaustive}",
        user_id=current_user.id, ip_address=_ip(request),
    )
    await db.commit()

    config = {
        "session_id":         session_id,
        "language":           session.language,
        "upload_path":        session.upload_path,
        "foss_project_id":    getattr(session, "foss_project_id", None),
        "loc":                session.loc or 5000,
        "test_count":         session.test_count or 100,
        "selected_operators": operators,
        "use_docker":         True,
        "factor_weights":     json.loads(session.weight_config) if getattr(session, "weight_config", None) else None,
    }

    # Resolve FOSS project slug for path lookup in worker
    foss_project_id = getattr(session, "foss_project_id", None)
    if foss_project_id:
        from sqlalchemy import select as _select
        from db.models.orm_models import FossProject
        fp_result = await db.execute(_select(FossProject).where(FossProject.id == foss_project_id))
        fp = fp_result.scalar_one_or_none()
        if fp:
            config["foss_slug"] = fp.slug
            config["loc"]       = fp.loc
            config["test_count"] = fp.test_count or 100

    from worker.celery_app import CELERY_AVAILABLE

    all_jobs = [primary_job] + ([exhaustive_job] if exhaustive_job else [])
    job_ids  = [j.id for j in all_jobs]

    for i, job in enumerate(all_jobs):
        job_config = {
            **config,
            "time_budget_seconds": job.time_budget_seconds,
            "optimizer_strategy":  job.optimizer_strategy,
            "strategy":            job.strategy,
        }
        countdown  = i * 90
        dispatched = False
        if CELERY_AVAILABLE:
            from worker.tasks import run_mutation_job
            try:
                task = run_mutation_job.apply_async(
                    args=[job.id, job_config],
                    countdown=countdown,
                )
                await job_repo.mark_running(job.id, task.id)
                await db.commit()
                dispatched = True
                log.info("Job %s (%s) dispatched (countdown=%ds)", job.id, job.strategy, countdown)
            except Exception as exc:
                log.warning("Celery dispatch failed, using thread: %s", exc)

        if not dispatched:
            import threading
            from worker.tasks import run_mutation_job_sync
            t = threading.Thread(
                target=run_mutation_job_sync,
                args=(job.id, job_config),
                daemon=True,
            )
            t.start()
            log.info("Job %s (%s) dispatched to thread", job.id, job.strategy)

    return {"session_id": session_id, "jobs": job_ids}


# ── Shareable link ─────────────────────────────────────────────────────────────

@router.post("/{session_id}/share", response_model=dict)
async def create_share_link(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """FR116: Generate shareable results link valid for 30 days."""
    repo    = TestSessionRepository(db)
    session = await repo.get_by_id(session_id)
    if not session or session.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status != "completed":
        raise HTTPException(status_code=400, detail="Can only share completed sessions.")

    token       = generate_secure_token(32)
    expires_at  = datetime.utcnow() + timedelta(days=30)
    await repo.update(session, share_token=token, share_expires_at=expires_at)
    await db.commit()

    share_url = f"{settings.FRONTEND_URL}/results/share/{token}"
    return {"share_url": share_url, "expires_at": expires_at.isoformat()}


@router.get("/share/{token}", response_model=SessionOut)
async def get_shared_session(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """FR116: Public view of shared session (no auth required)."""
    repo    = TestSessionRepository(db)
    session = await repo.get_by_share_token(token)
    if not session:
        raise HTTPException(status_code=404, detail="Shared results not found or link has expired.")
    if session.share_expires_at and datetime.utcnow() > session.share_expires_at:
        raise HTTPException(status_code=410, detail="This shared link has expired.")
    return session
