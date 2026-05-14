"""worker/celery_app.py"""
from __future__ import annotations
import logging

log = logging.getLogger(__name__)


def _is_tls(url: str) -> bool:
    return url.startswith("rediss://")


try:
    from celery import Celery
    from config.settings import get_settings

    s = get_settings()
    celery_app = Celery(
        "impt",
        broker=s.CELERY_BROKER_URL,
        backend=s.CELERY_RESULT_BACKEND,
        include=["worker.tasks"],
    )
    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        broker_connection_retry_on_startup=True,
        result_expires=86400,
    )
    if _is_tls(s.CELERY_BROKER_URL):
        celery_app.conf.update(
            broker_use_ssl={"ssl_cert_reqs": "required"},
            redis_backend_use_ssl={"ssl_cert_reqs": "required"},
        )
        log.info("Celery TLS enabled (Upstash)")

    CELERY_AVAILABLE = True
except Exception as exc:
    log.warning("Celery init failed (%s) — using sync fallback", exc)
    celery_app = None
    CELERY_AVAILABLE = False
