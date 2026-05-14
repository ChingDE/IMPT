"""worker/watchdog.py — Celery beat task to auto-fail stuck jobs."""
from __future__ import annotations
import logging

log = logging.getLogger(__name__)

try:
    from worker.celery_app import celery_app, CELERY_AVAILABLE
    from config.settings import get_settings

    if celery_app and CELERY_AVAILABLE:
        @celery_app.on_after_configure.connect
        def setup_periodic_tasks(sender, **kwargs):
            sender.add_periodic_task(300.0, check_stuck_jobs.s(),
                                     name="check-stuck-jobs")

        @celery_app.task(name="worker.watchdog.check_stuck_jobs")
        def check_stuck_jobs():
            import asyncio
            asyncio.run(_check())

        async def _check():
            from db.database import AsyncSessionLocal
            from db.repositories.repositories import JobRepository

            s       = get_settings()
            timeout = s.JOB_TIMEOUT_WATCHDOG_SECONDS

            async with AsyncSessionLocal() as db:
                repo  = JobRepository(db)
                stuck = await repo.get_stuck_jobs(timeout)
                for job in stuck:
                    await repo.mark_failed(job.id, f"Job timed out after {timeout}s")
                    log.warning("Watchdog auto-failed stuck job: %s", job.id)
                if stuck:
                    await db.commit()
                    log.info("Watchdog cleaned up %d stuck jobs", len(stuck))

    else:
        def check_stuck_jobs():
            pass

except Exception as exc:
    log.warning("Watchdog init failed: %s", exc)

    def check_stuck_jobs():
        pass
