"""api/routers/health.py"""
from fastapi import APIRouter
from db.database import AsyncSessionLocal
from sqlalchemy import text

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health():
    db_status = "error"
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        pass

    worker_status = "ok (sync)"
    try:
        from worker.celery_app import celery_app, CELERY_AVAILABLE
        if CELERY_AVAILABLE and celery_app:
            celery_app.control.ping(timeout=1.0)
            worker_status = "ok (celery)"
    except Exception:
        pass

    return {"status": "ok", "version": "2.0.0", "db": db_status, "worker": worker_status}
