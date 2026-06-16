"""
config/settings.py
All configuration read from environment variables.
Local dev defaults work without any .env file (SQLite + no Redis + no email).
"""
from __future__ import annotations
import os
from functools import lru_cache


class Settings:
    APP_NAME:    str = "IMPT — Intelligent Mutation Prioritization Tool"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool      = os.getenv("IMPT_DEBUG", "true").lower() == "true"

    # ── Database ──────────────────────────────────────────────────────
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "sqlite+aiosqlite:///./impt_local.db"
    )
    DATABASE_URL_SYNC: str = os.getenv(
        "DATABASE_URL_SYNC", "sqlite:///./impt_local.db"
    )

    # ── Redis / Celery ─────────────────────────────────────────────────
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    CELERY_BROKER_URL: str = os.getenv(
        "CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://localhost:6379/0")
    )
    CELERY_RESULT_BACKEND: str = os.getenv(
        "CELERY_RESULT_BACKEND", os.getenv("REDIS_URL", "redis://localhost:6379/0")
    )

    # ── Auth ───────────────────────────────────────────────────────────
    SECRET_KEY: str = os.getenv(
        "SECRET_KEY", "impt-dev-secret-key-change-in-production-32chars"
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
    )

    # ── Email — Gmail SMTP ─────────────────────────────────────────────
    SMTP_HOST:          str  = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT:          int  = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER:          str  = os.getenv("SMTP_USER", "")          # e.g. novasoft_impt@gmail.com
    SMTP_PASSWORD:      str  = os.getenv("SMTP_PASSWORD", "")       # 16-char Gmail App Password
    EMAIL_FROM:         str  = os.getenv("EMAIL_FROM", "IMPT <novasoft_impt@gmail.com>")
    EMAIL_ENABLED:      bool = bool(os.getenv("SMTP_USER", "") and os.getenv("SMTP_PASSWORD", ""))
    ADMIN_ALERT_EMAIL:  str  = os.getenv("ADMIN_ALERT_EMAIL", "")

    # ── Token expiry ───────────────────────────────────────────────────
    EMAIL_VERIFICATION_EXPIRE_HOURS: int = int(
        os.getenv("EMAIL_VERIFICATION_EXPIRE_HOURS", "24")
    )
    PASSWORD_RESET_EXPIRE_HOURS: int = int(
        os.getenv("PASSWORD_RESET_EXPIRE_HOURS", "1")
    )

    # ── Frontend URL (for email links) ─────────────────────────────────
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")

    # ── Upload / Storage ───────────────────────────────────────────────
    UPLOAD_DIR: str    = os.getenv("UPLOAD_DIR", "./uploads")
    MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "50"))
    MAX_UPLOAD_BYTES: int = MAX_UPLOAD_MB * 1024 * 1024

    # ── File retention ─────────────────────────────────────────────────
    FILE_RETENTION_DAYS: int = int(os.getenv("FILE_RETENTION_DAYS", "90"))

    # ── CORS ───────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: list = [
        o.strip()
        for o in os.getenv(
            "ALLOWED_ORIGINS",
            "http://localhost:3000,http://localhost:5173"
        ).split(",")
        if o.strip()
    ]

    # ── Rate limiting ──────────────────────────────────────────────────
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = int(
        os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE", "100")
    )
    LOGIN_MAX_ATTEMPTS: int = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
    LOGIN_LOCKOUT_MINUTES: int = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "15"))

    # ── Session timeout ────────────────────────────────────────────────
    SESSION_TIMEOUT_MINUTES: int = int(
        os.getenv("SESSION_TIMEOUT_MINUTES", "30")
    )
    SESSION_WARNING_MINUTES: int = int(
        os.getenv("SESSION_WARNING_MINUTES", "2")
    )

    # ── Watchdog ───────────────────────────────────────────────────────
    JOB_TIMEOUT_WATCHDOG_SECONDS: int = int(
        os.getenv("JOB_TIMEOUT_WATCHDOG_SECONDS", "3900")
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
