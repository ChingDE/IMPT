"""
worker/watchdog.py
Job Timeout Watchdog
=====================
A Celery beat periodic task that scans for jobs stuck in RUNNING or PENDING
status beyond JOB_TIMEOUT_WATCHDOG_SECONDS and marks them FAILED.

This handles the case where a Celery worker crashes mid-job, leaving the
job record in RUNNING forever.

Schedule: runs every 5 minutes via Celery beat.
Activate with:
    celery -A worker.celery_app.celery_app beat -l info &
    celery -A worker.celery_app.celery_app worker -l info
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)


async def _mark_timed_out_jobs() -> int:
    """
    Find all jobs in RUNNING or PENDING status whose started_at (or
    created_at for PENDING) is older than the watchdog threshold and
    mark them FAILED.

    Returns the number of jobs marked.
    """
    from config.settings import get_settings
    from db.database import AsyncSessionLocal
    from db.repositories import JobRepository
    from sqlalchemy import select, update
    from db.models.orm_models import MutationJob

    settings = get_settings()
    threshold = timedelta(seconds=settings.JOB_TIMEOUT_WATCHDOG_SECONDS)
    cutoff    = datetime.now(timezone.utc) - threshold

    async with AsyncSessionLocal() as session:
        # Find stuck jobs
        result = await session.execute(
            select(MutationJob).where(
                MutationJob.status.in_(["RUNNING", "PENDING"]),
                MutationJob.created_at < cutoff,
            )
        )
        stuck = result.scalars().all()

        count = 0
        for job in stuck:
            await session.execute(
                update(MutationJob)
                .where(MutationJob.id == job.id)
                .values(
                    status="FAILED",
                    completed_at=datetime.now(timezone.utc),
                    error_message=(
                        f"Job timed out after {settings.JOB_TIMEOUT_WATCHDOG_SECONDS}s "
                        f"(watchdog). Original status: {job.status}"
                    ),
                )
            )
            count += 1
            log.warning(
                "Watchdog: marked job %s as FAILED (was %s since %s)",
                job.id, job.status, job.created_at,
            )

        await session.commit()
        return count


# ── Celery beat task ──────────────────────────────────────────────────────────

try:
    from worker.celery_app import celery_app, CELERY_AVAILABLE
    import asyncio

    if celery_app and CELERY_AVAILABLE:
        @celery_app.task(name="worker.watchdog.check_stuck_jobs")
        def check_stuck_jobs() -> dict:
            """Periodic task: recover stuck jobs."""
            count = asyncio.get_event_loop().run_until_complete(
                _mark_timed_out_jobs()
            )
            log.info("Watchdog: marked %d stuck jobs as FAILED", count)
            return {"marked_failed": count}

        # Configure Celery beat schedule
        celery_app.conf.beat_schedule = {
            "check-stuck-jobs": {
                "task":     "worker.watchdog.check_stuck_jobs",
                "schedule": 300.0,   # every 5 minutes
            },
        }
        celery_app.conf.timezone = "UTC"

except Exception as exc:
    log.debug("Watchdog Celery registration skipped: %s", exc)
