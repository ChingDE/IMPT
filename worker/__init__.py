from worker.celery_app import celery_app, CELERY_AVAILABLE

__all__ = ["celery_app", "CELERY_AVAILABLE"]

from worker import watchdog  # noqa: F401 — registers beat task
