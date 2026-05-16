"""main.py — IMPT FastAPI application."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.middleware import RateLimitMiddleware, RequestSizeMiddleware
from config.settings import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("IMPT v2 starting…")

    # Create all tables
    from db.database import create_tables
    await create_tables()
    log.info("Database tables ready.")

    # Seed default admin
    from db.database import AsyncSessionLocal
    from db.seed import seed_admin
    async with AsyncSessionLocal() as db:
        await seed_admin(db)

    # Seed default system config
    async with AsyncSessionLocal() as db:
        await _seed_config(db)

    log.info("IMPT v2 ready.")
    yield
    log.info("IMPT v2 shutting down.")


async def _seed_config(db):
    from db.repositories.repositories import SystemConfigRepository
    repo = SystemConfigRepository(db)
    defaults = {
        "max_upload_mb":               "50",
        "session_timeout_minutes":     "30",
        "password_reset_expire_hours": "1",
        "email_verify_expire_hours":   "24",
        "file_retention_days":         "90",
        "registration_enabled":        "true",
    }
    for key, value in defaults.items():
        existing = await repo.get(key)
        if not existing:
            await repo.set(key, value)
    await db.commit()


def create_app() -> FastAPI:
    app = FastAPI(
        title="IMPT — Intelligent Mutation Prioritization Tool",
        version="2.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Middleware (order: outermost first)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestSizeMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    from api.routers.auth      import router as auth_router
    from api.routers.sessions  import router as sessions_router
    from api.routers.jobs      import router as jobs_router
    from api.routers.users     import router as users_router
    from api.routers.admin     import router as admin_router
    from api.routers.analytics import router as analytics_router
    from api.routers.health    import router as health_router
    from api.routers.foss      import router as foss_router
    from api.routers.ws        import router as ws_router

    app.include_router(auth_router)
    app.include_router(sessions_router)
    app.include_router(jobs_router)
    app.include_router(users_router)
    app.include_router(admin_router)
    app.include_router(analytics_router)
    app.include_router(health_router)
    app.include_router(foss_router)
    app.include_router(ws_router)

    return app


app = create_app()
