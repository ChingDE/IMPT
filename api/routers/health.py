"""
api/routers/health.py
GET /api/health — service health check.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas import HealthOut
from config.settings import get_settings
from db.database import get_db

router = APIRouter(prefix="/api", tags=["health"])
settings = get_settings()


@router.get("/health", response_model=HealthOut)
async def health(db: AsyncSession = Depends(get_db)):
    # DB ping
    try:
        await db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:  # noqa: BLE001
        db_status = f"error: {exc}"

    # Worker ping
    try:
        from worker.celery_app import CELERY_AVAILABLE
        worker_status = "ok (celery)" if CELERY_AVAILABLE else "ok (sync-fallback)"
    except Exception:
        worker_status = "unknown"

    return HealthOut(
        status="ok",
        version=settings.APP_VERSION,
        db=db_status,
        worker=worker_status,
    )
