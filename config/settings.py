"""
config/settings.py
Central configuration — all values read from environment variables.

Local dev defaults work without any .env file (SQLite + no Redis).
Production values come from the .env file on the DigitalOcean Droplet.
"""

from __future__ import annotations

import os
from functools import lru_cache


class Settings:
    APP_NAME:    str = "IMPT — Intelligent Mutation Prioritization Tool"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool      = os.getenv("IMPT_DEBUG", "true").lower() == "true"

    # ── Database ──────────────────────────────────────────────────────────────
    # Production  → DigitalOcean Managed PostgreSQL (set in .env)
    # Local dev   → SQLite (no setup required)
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "sqlite+aiosqlite:///./impt_local.db"
    )
    DATABASE_URL_SYNC: str = os.getenv(
        "DATABASE_URL_SYNC", "sqlite:///./impt_local.db"
    )

    # ── Redis / Celery ────────────────────────────────────────────────────────
    # Production  → Upstash (rediss:// TLS — handled automatically in celery_app.py)
    # Local dev   → localhost plain Redis, or sync fallback if Redis is absent
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    CELERY_BROKER_URL: str = os.getenv(
        "CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://localhost:6379/0")
    )
    CELERY_RESULT_BACKEND: str = os.getenv(
        "CELERY_RESULT_BACKEND", os.getenv("REDIS_URL", "redis://localhost:6379/0")
    )

    # ── Auth ──────────────────────────────────────────────────────────────────
    SECRET_KEY: str = os.getenv(
        "SECRET_KEY", "impt-dev-secret-key-change-in-production-32chars"
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
    )

    # ── Upload / Storage ──────────────────────────────────────────────────────
    UPLOAD_DIR: str    = os.getenv("UPLOAD_DIR", "./uploads")
    MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "50"))
    MAX_UPLOAD_BYTES: int = MAX_UPLOAD_MB * 1024 * 1024

    # ── CORS ──────────────────────────────────────────────────────────────────
    # Production  → your Vercel URL + custom domain (set in .env)
    # Local dev   → localhost dev servers
    ALLOWED_ORIGINS: list = [
        o.strip()
        for o in os.getenv(
            "ALLOWED_ORIGINS",
            "http://localhost:3000,http://localhost:5173"
        ).split(",")
        if o.strip()
    ]

    # ── Rate limiting ─────────────────────────────────────────────────────────
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = int(
        os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE", "60")
    )

    # ── Engine defaults ───────────────────────────────────────────────────────
    DEFAULT_TIME_BUDGET_SECONDS: int = 1800
    MIN_TIME_BUDGET_SECONDS: int     = 60
    MAX_TIME_BUDGET_SECONDS: int     = 3600

    # ── Watchdog ──────────────────────────────────────────────────────────────
    JOB_TIMEOUT_WATCHDOG_SECONDS: int = int(
        os.getenv("JOB_TIMEOUT_WATCHDOG_SECONDS", "3900")
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
