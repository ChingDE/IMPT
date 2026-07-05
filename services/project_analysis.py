"""services/project_analysis.py — shared post-extraction project analysis.

Given an extracted project directory, this locates the real build root, computes
metadata (source file count, LOC, test count), detects the framework, estimates
mutant count + budget, persists everything onto the session, and dispatches the
best-effort live coverage measurement. Used by the GitHub import endpoint so it
produces exactly the same session state as a ZIP upload.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import HTTPException

from services.metadata import count_source_files

log = logging.getLogger(__name__)


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
        for _ in root.rglob("*.test.*"):
            count += 1
        for _ in root.rglob("*.spec.*"):
            count += 1
    return count


def _resolve_build_root(extracted: Path, language: str) -> tuple[Path, str]:
    """Find the project's build root and framework, mirroring the ZIP-upload checks."""
    root = extracted
    items = [p for p in extracted.iterdir()]
    if len(items) == 1 and items[0].is_dir():
        root = items[0]

    if language == "java":
        builds = [p for p in (list(root.rglob("pom.xml")) + list(root.rglob("build.gradle")))
                  if "node_modules" not in str(p)]
        if not builds:
            raise HTTPException(status_code=422,
                detail="No Java build file (pom.xml or build.gradle) found in the repository.")
        builds.sort(key=lambda p: len(p.parts))
        return builds[0].parent, "PIT"
    else:
        pkgs = [p for p in root.rglob("package.json") if "node_modules" not in str(p)]
        if not pkgs:
            raise HTTPException(status_code=422,
                detail="No package.json found in the repository. Expected a JavaScript/Node.js project.")
        pkgs.sort(key=lambda p: len(p.parts))
        return pkgs[0].parent, "Stryker"


def _dispatch_coverage(session_id: str, project_root: str, language: str) -> None:
    """Best-effort live coverage measurement, off the mutation pipeline."""
    try:
        from worker.celery_app import CELERY_AVAILABLE
        if CELERY_AVAILABLE:
            from worker.tasks import measure_coverage
            measure_coverage.apply_async(args=[session_id, project_root, language])
            return
    except Exception as exc:
        log.warning("coverage celery dispatch failed (%s); using thread", exc)
    try:
        import threading
        from worker.tasks import measure_coverage_sync
        threading.Thread(target=measure_coverage_sync,
                         args=(session_id, project_root, language), daemon=True).start()
    except Exception as exc:
        log.warning("coverage dispatch failed for %s: %s", session_id, exc)


async def analyze_into_session(db, repo, session, extracted_dir: Path, *,
                               language: str, source_label: str, size_bytes: int,
                               subdir: Optional[str] = None):
    """Analyze an extracted project and persist results onto the session.

    `repo` is a TestSessionRepository; `session` the ORM row. Returns the
    updated session. Raises HTTPException(422) if the project is not valid.
    """
    base = extracted_dir
    if subdir:
        sub = (extracted_dir / subdir).resolve()
        if not str(sub).startswith(str(extracted_dir.resolve())) or not sub.exists():
            raise HTTPException(status_code=422, detail="Invalid subdirectory for this repository.")
        base = sub

    project_root, framework = _resolve_build_root(base, language)

    file_count = count_source_files(project_root, language)
    loc        = _count_loc(project_root, language)
    test_count = _count_tests(project_root, language)

    mutant_rate = 12 if language == "java" else 10
    est_mutants = max(10, int(loc / 1000 * mutant_rate))
    raw_rec     = max(5, min(120, int(est_mutants / 20)))
    rec_min     = max(5, raw_rec - 5)
    rec_max     = min(120, raw_rec + 10)

    updated = await repo.update(
        session,
        upload_path=str(project_root),
        upload_filename=source_label,
        upload_size_bytes=size_bytes,
        file_count=file_count,
        loc=loc,
        test_count=test_count,
        test_coverage=None,
        detected_framework=framework,
        estimated_mutant_count=est_mutants,
        recommended_budget_min=rec_min,
        recommended_budget_max=rec_max,
        status="uploaded",
    )
    await db.commit()
    _dispatch_coverage(session.id, str(project_root), language)
    return updated
