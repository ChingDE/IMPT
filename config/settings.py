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

    # ── Email — Gmail API (HTTPS / OAuth2) ─────────────────
    GMAIL_CLIENT_ID:     str  = os.getenv("GMAIL_CLIENT_ID", "")
    GMAIL_CLIENT_SECRET: str  = os.getenv("GMAIL_CLIENT_SECRET", "")
    GMAIL_REFRESH_TOKEN: str  = os.getenv("GMAIL_REFRESH_TOKEN", "")
    EMAIL_FROM:          str  = os.getenv("EMAIL_FROM", "IMPT <novasoft.impt@gmail.com>")
    EMAIL_ENABLED:       bool = bool(
        os.getenv("GMAIL_CLIENT_ID", "")
        and os.getenv("GMAIL_CLIENT_SECRET", "")
        and os.getenv("GMAIL_REFRESH_TOKEN", "")
    )
    ADMIN_ALERT_EMAIL:   str  = os.getenv("ADMIN_ALERT_EMAIL", "")

    # ── Token expiry ───────────────────────────────────────────────────
    EMAIL_VERIFICATION_EXPIRE_HOURS: int = int(
        os.getenv("EMAIL_VERIFICATION_EXPIRE_HOURS", "24")
    )
    PASSWORD_RESET_EXPIRE_HOURS: int = int(
        os.getenv("PASSWORD_RESET_EXPIRE_HOURS", "1")
    )

    # ── Frontend URL (for email links) ─────────────────────────────────
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")

    # ── GitHub account linking ─────────────────────────────────────────
    # Public base URL of THIS API (where GitHub sends the OAuth callback).
    API_BASE_URL: str = os.getenv("API_BASE_URL", "http://localhost:8000")
    GITHUB_CLIENT_ID: str     = os.getenv("GITHUB_CLIENT_ID", "")
    GITHUB_CLIENT_SECRET: str = os.getenv("GITHUB_CLIENT_SECRET", "")
    GITHUB_OAUTH_SCOPE: str   = os.getenv("GITHUB_OAUTH_SCOPE", "repo")   # 'repo' = private+public
    GITHUB_TOKEN_KEY: str     = os.getenv("GITHUB_TOKEN_KEY", "")         # optional Fernet key; else derived from SECRET_KEY
    GITHUB_MAX_IMPORT_MB: int = int(os.getenv("GITHUB_MAX_IMPORT_MB", "200"))
    GITHUB_ENABLED: bool      = bool(os.getenv("GITHUB_CLIENT_ID", "") and os.getenv("GITHUB_CLIENT_SECRET", ""))

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
    # Sign-in, registration and password-reset endpoints (NFR008 default: 10)
    RATE_LIMIT_AUTH_PER_MINUTE: int = int(
        os.getenv("RATE_LIMIT_AUTH_PER_MINUTE", "10")
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
