"""
api/middleware.py
Security middleware for the IMPT FastAPI application.

Provides:
  - RateLimitMiddleware  — per-IP sliding window rate limit (in-memory, no Redis dep)
  - RequestSizeMiddleware — enforce MAX_UPLOAD_BYTES hard limit at middleware level

Both are lightweight and have no external dependencies.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from config.settings import get_settings

settings = get_settings()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding window rate limiter.
    Allows up to `max_requests` per `window_seconds` per client IP.
    Auth endpoints have a tighter limit to slow brute-force attempts.

    Note: Uses an in-memory store — resets on restart and is not shared
    across multiple API workers. For multi-worker deployments, swap the
    store with a Redis-backed solution using the same interface.
    """

    def __init__(
        self,
        app: ASGIApp,
        max_requests: int = 60,
        window_seconds: int = 60,
        auth_max_requests: int = 10,   # stricter limit for /api/auth/token
    ) -> None:
        super().__init__(app)
        self.max_requests      = max_requests
        self.window_seconds    = window_seconds
        self.auth_max_requests = auth_max_requests
        # ip → deque of request timestamps
        self._store: defaultdict[str, deque] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip rate-limiting for health checks
        if request.url.path in ("/api/health", "/", "/docs", "/redoc", "/openapi.json"):
            return await call_next(request)

        ip    = self._get_ip(request)
        now   = time.monotonic()
        limit = (
            self.auth_max_requests
            if "/auth/token" in request.url.path
            else self.max_requests
        )

        window = self._store[ip]
        # Evict timestamps outside the current window
        cutoff = now - self.window_seconds
        while window and window[0] < cutoff:
            window.popleft()

        if len(window) >= limit:
            retry_after = int(self.window_seconds - (now - window[0])) + 1
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down."},
                headers={"Retry-After": str(retry_after)},
            )

        window.append(now)
        return await call_next(request)

    @staticmethod
    def _get_ip(request: Request) -> str:
        # Respect X-Forwarded-For from Nginx
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"


class RequestSizeMiddleware(BaseHTTPMiddleware):
    """
    Rejects requests whose Content-Length exceeds MAX_UPLOAD_BYTES.
    Provides a clean 413 before FastAPI even reads the body.
    Only enforced on upload endpoints to avoid blocking small API calls.
    """

    UPLOAD_PATHS = ("/upload",)

    def __init__(self, app: ASGIApp, max_bytes: int = 0) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes or settings.MAX_UPLOAD_BYTES

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if any(seg in request.url.path for seg in self.UPLOAD_PATHS):
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > self.max_bytes:
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": (
                            f"Request body too large. "
                            f"Maximum upload size is {settings.MAX_UPLOAD_MB} MB."
                        )
                    },
                )
        return await call_next(request)
