"""
worker/celery_app.py
Celery application.

Cloud production:  broker = Upstash Redis (rediss:// with TLS)
Local dev:         broker = local Redis (redis://) or sync fallback if unavailable
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)


def _is_tls_url(url: str) -> bool:
    return url.startswith("rediss://")


try:
    from celery import Celery
    from config.settings import get_settings

    settings = get_settings()

    celery_app = Celery(
        "impt",
        broker=settings.CELERY_BROKER_URL,
        backend=settings.CELERY_RESULT_BACKEND,
        include=["worker.tasks"],
    )

    # ── Base config ───────────────────────────────────────────────────────────
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

    # ── TLS — required for Upstash (rediss://) ─────────────────────────────────
    # Enabled automatically when the broker URL uses the rediss:// scheme.
    # No change needed when running locally with plain redis://.
    if _is_tls_url(settings.CELERY_BROKER_URL):
        celery_app.conf.update(
            broker_use_ssl={"ssl_cert_reqs": "required"},
            redis_backend_use_ssl={"ssl_cert_reqs": "required"},
        )
        log.info("Celery TLS enabled (Upstash / rediss://)")

    CELERY_AVAILABLE = True
    log.info("Celery app initialised (broker=%s)", settings.CELERY_BROKER_URL)

except Exception as exc:  # noqa: BLE001
    log.warning("Celery init failed (%s) — using sync fallback", exc)
    celery_app = None   # type: ignore[assignment]
    CELERY_AVAILABLE = False
