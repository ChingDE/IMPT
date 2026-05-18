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


# ── NFR081: Scheduled temp file and old upload cleanup ───────────────────────
@celery_app.task(name='worker.watchdog.cleanup_old_files')
def cleanup_old_files():
    """
    NFR081: Delete project files for sessions older than 90 days
    and temp files older than 24 hours.
    Runs daily via Celery beat.
    """
    import shutil
    from pathlib import Path
    from datetime import datetime, timedelta
    import logging

    log = logging.getLogger(__name__)
    now = datetime.utcnow()
    deleted_dirs = 0
    deleted_tmp  = 0

    # Clean foss-tmp sandbox directories older than 24h
    foss_tmp = Path('/app/foss-tmp')
    if foss_tmp.exists():
        for d in foss_tmp.iterdir():
            if d.is_dir():
                try:
                    mtime = datetime.utcfromtimestamp(d.stat().st_mtime)
                    if now - mtime > timedelta(hours=24):
                        # Only remove stryker sandbox dirs, not foss project workdirs
                        for sd in d.glob('.stryker-tmp/sandbox-*'):
                            shutil.rmtree(sd, ignore_errors=True)
                            deleted_tmp += 1
                except Exception as e:
                    log.warning("cleanup_old_files: could not clean %s: %s", d, e)

    # Clean user-uploaded project temp dirs older than 90 days
    uploads_dir = Path('/app/uploads')
    if uploads_dir.exists():
        cutoff = now - timedelta(days=90)
        for session_dir in uploads_dir.iterdir():
            if session_dir.is_dir():
                try:
                    mtime = datetime.utcfromtimestamp(session_dir.stat().st_mtime)
                    if mtime < cutoff:
                        shutil.rmtree(session_dir, ignore_errors=True)
                        deleted_dirs += 1
                except Exception as e:
                    log.warning("cleanup_old_files: could not delete %s: %s", session_dir, e)

    log.info("cleanup_old_files: removed %d upload dirs, %d sandbox dirs", deleted_dirs, deleted_tmp)
    return {'deleted_upload_dirs': deleted_dirs, 'deleted_sandbox_dirs': deleted_tmp}


# Register with beat schedule
@celery_app.on_after_finalize.connect
def setup_periodic_tasks_extended(sender, **kwargs):
    # Run cleanup daily at 03:00 UTC
    sender.add_periodic_task(
        86400.0,  # every 24 hours
        cleanup_old_files.s(),
        name='daily-file-cleanup'
    )
