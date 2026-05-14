"""api/middleware.py — Security middleware."""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from config.settings import get_settings

log = logging.getLogger(__name__)
settings = get_settings()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding window rate limiter.
    NFR008: 100 req/min general, 10 req/min for auth/upload endpoints.
    """

    def __init__(self, app):
        super().__init__(app)
        self._windows: dict = defaultdict(deque)
        self._exempt = {"/api/health", "/docs", "/redoc", "/openapi.json"}
        self._tight  = {"/api/auth/token", "/api/auth/register", "/api/auth/admin-token",
                        "/api/auth/forgot-password", "/api/auth/reset-password"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Exempt paths
        if path in self._exempt or path.startswith("/docs"):
            return await call_next(request)

        ip  = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
        key = f"{ip}:{path}"
        now = time.monotonic()

        window_size = 60  # seconds
        limit = 10 if path in self._tight else settings.RATE_LIMIT_REQUESTS_PER_MINUTE

        dq = self._windows[key]
        while dq and dq[0] < now - window_size:
            dq.popleft()

        if len(dq) >= limit:
            retry_after = int(window_size - (now - dq[0]))
            return Response(
                content='{"detail": "Too many requests. Please wait before retrying."}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": str(retry_after)},
            )

        dq.append(now)
        return await call_next(request)


class RequestSizeMiddleware(BaseHTTPMiddleware):
    """Reject oversized uploads before FastAPI reads the body."""

    async def dispatch(self, request: Request, call_next):
        if "upload" in request.url.path:
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > settings.MAX_UPLOAD_BYTES:
                return Response(
                    content=f'{{"detail": "File size exceeds {settings.MAX_UPLOAD_MB}MB limit."}}',
                    status_code=413,
                    media_type="application/json",
                )
        return await call_next(request)
