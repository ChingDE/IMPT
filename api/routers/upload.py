"""
api/routers/upload.py
Project file upload endpoint
==============================
POST /api/projects/{project_id}/upload
  - Accepts .zip or .tar.gz containing a Java or JavaScript project
  - Validates size, extension, and internal structure
  - Extracts to uploads/{user_id}/{project_id}/
  - Scans LOC and test count
  - Updates the ProjectRecord with upload_path, loc, test_count
"""

from __future__ import annotations

import logging
import os
import shutil
import tarfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user
from api.schemas import ProjectOut
from config.settings import get_settings
from db.database import get_db
from db.models.orm_models import User
from db.repositories import ProjectRepository

log      = logging.getLogger(__name__)
router   = APIRouter(prefix="/api/projects", tags=["upload"])
settings = get_settings()

ALLOWED_EXTENSIONS = {".zip", ".tar.gz", ".tgz"}
MAX_SIZE_BYTES     = settings.MAX_UPLOAD_BYTES


@router.post("/{project_id}/upload", response_model=ProjectOut)
async def upload_project(
    project_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a .zip or .tar.gz containing the source project.
    The file is extracted and the project record is updated.
    """
    # ── Verify ownership ──────────────────────────────────────────────────────
    repo    = ProjectRepository(db)
    project = await repo.get_by_id(project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    # ── Validate file extension ───────────────────────────────────────────────
    filename = file.filename or ""
    if not _valid_extension(filename):
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # ── Read and size-check ───────────────────────────────────────────────────
    content = await file.read()
    if len(content) > MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum: {settings.MAX_UPLOAD_MB} MB",
        )

    # ── Prepare destination ───────────────────────────────────────────────────
    dest_dir = Path(settings.UPLOAD_DIR) / current_user.id / project_id
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    archive_path = dest_dir / filename
    archive_path.write_bytes(content)

    # ── Extract ───────────────────────────────────────────────────────────────
    try:
        extract_dir = dest_dir / "source"
        extract_dir.mkdir(exist_ok=True)
        _extract_archive(archive_path, extract_dir)
    except Exception as exc:
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise HTTPException(
            status_code=422,
            detail=f"Could not extract archive: {exc}",
        )

    # ── Find project root (unwrap single top-level dir if present) ────────────
    project_root = _find_project_root(extract_dir)

    # ── Validate structure ────────────────────────────────────────────────────
    framework = project.framework.upper()
    _validate_structure(project_root, framework, project_id)

    # ── Scan metrics ──────────────────────────────────────────────────────────
    loc, test_count = _scan_metrics(project_root, framework)

    # ── Update project record ─────────────────────────────────────────────────
    project.upload_path = str(project_root)
    project.loc         = loc
    project.test_count  = test_count
    db.add(project)

    log.info(
        "Uploaded project %s → %s (LOC=%d, tests=%d)",
        project_id, project_root, loc, test_count,
    )
    return project


# ── Helpers ───────────────────────────────────────────────────────────────────

def _valid_extension(filename: str) -> bool:
    fn = filename.lower()
    return fn.endswith(".zip") or fn.endswith(".tar.gz") or fn.endswith(".tgz")


def _extract_archive(archive_path: Path, dest: Path) -> None:
    fn = archive_path.name.lower()
    if fn.endswith(".zip"):
        with zipfile.ZipFile(archive_path, "r") as zf:
            # Security: reject absolute paths and path traversal
            for member in zf.namelist():
                if os.path.isabs(member) or ".." in member:
                    raise ValueError(f"Unsafe path in archive: {member}")
            zf.extractall(dest)
    elif fn.endswith(".tar.gz") or fn.endswith(".tgz"):
        with tarfile.open(archive_path, "r:gz") as tf:
            for member in tf.getmembers():
                if os.path.isabs(member.name) or ".." in member.name:
                    raise ValueError(f"Unsafe path in archive: {member.name}")
            tf.extractall(dest)
    else:
        raise ValueError("Unknown archive format")


def _find_project_root(extract_dir: Path) -> Path:
    """
    If the archive had a single top-level directory, return that.
    Otherwise return the extract dir itself.
    """
    entries = [e for e in extract_dir.iterdir() if not e.name.startswith(".")]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return extract_dir


def _validate_structure(root: Path, framework: str, project_id: str) -> None:
    """Raise 422 if the project lacks the expected structure."""
    if framework == "PIT":
        has_maven  = (root / "pom.xml").exists()
        has_gradle = (root / "build.gradle").exists() or (root / "build.gradle.kts").exists()
        if not has_maven and not has_gradle:
            raise HTTPException(
                status_code=422,
                detail="Java project must contain pom.xml or build.gradle",
            )
    else:  # STRYKER
        if not (root / "package.json").exists():
            raise HTTPException(
                status_code=422,
                detail="JavaScript project must contain package.json",
            )


def _scan_metrics(root: Path, framework: str) -> tuple[int, int]:
    """Scan LOC and test count. Returns (0, 0) on failure."""
    try:
        if framework == "PIT":
            from adapters.pit_adapter import PITAdapter
            a = PITAdapter(root, use_docker=False)
        else:
            from adapters.stryker_adapter import StrykerAdapter
            a = StrykerAdapter(root, use_docker=False)
        return a.count_loc(), a.count_tests()
    except Exception as exc:
        log.warning("Metric scan failed: %s", exc)
        return 0, 0
