"""
main.py
FastAPI application factory and entry point.

Run locally:
    uvicorn main:app --reload --port 8000

Or with the helper script:
    python scripts/run_local.py
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import auth_router, health_router, jobs_router, projects_router, upload_router, profiles_router, analytics_router, users_router
from api.middleware import RateLimitMiddleware, RequestSizeMiddleware
from config.settings import get_settings
from db.database import create_tables

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger(__name__)
settings = get_settings()


# ── Lifespan (startup / shutdown) ────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("IMPT API starting …")
    await create_tables()
    log.info("Database tables ready.")

    # Seed default admin account (no-op if it already exists)
    from db.database import AsyncSessionLocal
    from db.seed import seed_admin
    async with AsyncSessionLocal() as db:
        await seed_admin(db)

    yield
    log.info("IMPT API shutting down.")


# ── App factory ──────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "Intelligent Mutation Prioritization Tool — REST API\n\n"
            "NovaSoft | FEU Institute of Technology"
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Security middleware (applied before CORS)
    app.add_middleware(RateLimitMiddleware,
        max_requests=settings.RATE_LIMIT_REQUESTS_PER_MINUTE)
    app.add_middleware(RequestSizeMiddleware)

    # CORS — allow local frontend dev servers
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(projects_router)
    app.include_router(jobs_router)
    app.include_router(upload_router)
    app.include_router(profiles_router)
    app.include_router(analytics_router)
    app.include_router(users_router)

    @app.get("/", include_in_schema=False)
    async def root():
        return {
            "service": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "docs":    "/docs",
            "health":  "/api/health",
        }

    return app


app = create_app()
