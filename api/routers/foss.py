"""api/routers/foss.py — FOSS project catalogue and exhaustive baseline endpoints."""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.auth import get_current_user
from db.database import get_db
from db.models.orm_models import ExhaustiveBaseline, FossProject, User

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/foss", tags=["foss"])


def _project_out(p: FossProject) -> dict:
    b = p.baseline
    return {
        "id":           p.id,
        "slug":         p.slug,
        "name":         p.name,
        "description":  p.description,
        "language":     p.language,
        "domain":       p.domain,
        "github_url":   p.github_url,
        "license":      p.license,
        "loc":          p.loc,
        "size_band":    p.size_band,
        "test_count":   p.test_count,
        "file_count":     p.file_count,
        "test_coverage":  p.test_coverage,
        "version":      p.version,
        "has_baseline": b is not None,
        "baseline_mutation_score":          b.mutation_score if b else None,
        "baseline_total_mutants":           b.total_mutants if b else None,
        "baseline_killed_mutants":          b.killed_mutants if b else None,
        "baseline_execution_time_seconds":  b.execution_time_seconds if b else None,
        "baseline_source":                  b.source if b else None,
        "baseline_operator_breakdown":      b.operator_breakdown if b else None,
        "baseline_equivalent_mutants":      b.equivalent_mutants if b else 0,
        "baseline_computed_at":             b.computed_at.isoformat() if b else None,
    }


@router.get("", response_model=List[dict])
async def list_foss_projects(
    language: Optional[str] = None,
    size_band: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all active FOSS projects with their baseline status."""
    stmt = (
        select(FossProject)
        .options(selectinload(FossProject.baseline))
        .where(FossProject.is_active == True)
        .order_by(FossProject.language, FossProject.loc)
    )
    if language:
        stmt = stmt.where(FossProject.language == language)
    if size_band:
        stmt = stmt.where(FossProject.size_band == size_band)

    result = await db.execute(stmt)
    projects = result.scalars().all()
    return [_project_out(p) for p in projects]


@router.get("/{slug}", response_model=dict)
async def get_foss_project(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single FOSS project by slug."""
    stmt = (
        select(FossProject)
        .options(selectinload(FossProject.baseline))
        .where(FossProject.slug == slug, FossProject.is_active == True)
    )
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="FOSS project not found")
    return _project_out(project)


@router.get("/{slug}/baseline", response_model=dict)
async def get_exhaustive_baseline(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the pre-computed exhaustive baseline for a FOSS project."""
    stmt = (
        select(FossProject)
        .options(selectinload(FossProject.baseline))
        .where(FossProject.slug == slug)
    )
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="FOSS project not found")
    if not project.baseline:
        raise HTTPException(status_code=404, detail="No exhaustive baseline computed yet for this project")
    return _project_out(project)
