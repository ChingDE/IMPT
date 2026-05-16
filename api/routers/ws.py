"""api/routers/ws.py — WebSocket endpoint for real-time session progress.

Architecture:
  Worker  →  Redis pub/sub (channel: impt:session:{id})  →  FastAPI WS  →  Browser

The worker publishes JSON progress messages to the Redis channel.
The WebSocket handler subscribes and forwards them to the connected client.
Falls back to DB polling if Redis pub/sub is unavailable.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from config.settings import get_settings
from db.database import AsyncSessionLocal
from db.models.orm_models import MutationJob, TestSession

log     = logging.getLogger(__name__)
router  = APIRouter()
settings = get_settings()


def _channel(session_id: str) -> str:
    return f"impt:session:{session_id}"


async def _get_jobs_snapshot(session_id: str) -> list[dict]:
    """Read current job statuses from DB."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(MutationJob).where(MutationJob.session_id == session_id)
        )
        jobs = result.scalars().all()
        return [
            {
                "id":                     j.id,
                "strategy":               j.strategy,
                "status":                 j.status,
                "total_mutants":          j.total_mutants or 0,
                "executed_mutants":       j.executed_mutants or 0,
                "killed_mutants":         j.killed_mutants or 0,
                "mutation_score":         j.mutation_score or 0,
                "time_saved_pct":         j.time_saved_pct or 0,
                "execution_time_seconds": j.execution_time_seconds or 0,
                "estimated_score":        j.estimated_score or 0,
            }
            for j in jobs
        ]


@router.websocket("/api/ws/sessions/{session_id}")
async def session_progress_ws(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time mutation testing progress.
    Sends a snapshot immediately on connect, then streams live updates
    via Redis pub/sub. Falls back to polling if Redis unavailable.
    """
    await websocket.accept()
    log.info("WS connected for session %s", session_id)

    # Send immediate snapshot so client has something to render
    try:
        snapshot = await _get_jobs_snapshot(session_id)
        await websocket.send_json({"type": "snapshot", "jobs": snapshot})
    except Exception as e:
        log.warning("WS snapshot failed: %s", e)

    # Try Redis pub/sub first
    redis_client = None
    try:
        import redis.asyncio as aioredis
        redis_client = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=3,
        )
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(_channel(session_id))
        log.info("WS subscribed to Redis channel %s", _channel(session_id))

        async def _redis_loop():
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        await websocket.send_json(data)
                        # If all jobs done, close
                        if data.get("type") == "complete":
                            break
                    except Exception as e:
                        log.warning("WS send error: %s", e)
                        break

        async def _poll_loop():
            """Fallback polling every 3s in case Redis messages are missed."""
            while True:
                await asyncio.sleep(3)
                try:
                    jobs = await _get_jobs_snapshot(session_id)
                    await websocket.send_json({"type": "poll", "jobs": jobs})
                    all_done = all(
                        j["status"] in ("COMPLETED", "FAILED") for j in jobs
                    ) if jobs else False
                    if all_done:
                        await websocket.send_json({"type": "complete", "jobs": jobs})
                        break
                except Exception:
                    break

        # Run both concurrently — Redis for real-time, poll as safety net
        await asyncio.gather(
            _redis_loop(),
            _poll_loop(),
            return_exceptions=True,
        )

    except Exception as e:
        log.warning("Redis pub/sub unavailable (%s), falling back to DB polling", e)
        # Pure polling fallback
        while True:
            try:
                await asyncio.sleep(3)
                jobs = await _get_jobs_snapshot(session_id)
                await websocket.send_json({"type": "poll", "jobs": jobs})
                all_done = all(
                    j["status"] in ("COMPLETED", "FAILED") for j in jobs
                ) if jobs else False
                if all_done:
                    await websocket.send_json({"type": "complete", "jobs": jobs})
                    break
            except WebSocketDisconnect:
                break
            except Exception as exc:
                log.warning("WS poll error: %s", exc)
                break

    finally:
        if redis_client:
            try:
                await pubsub.unsubscribe(_channel(session_id))
                await redis_client.aclose()
            except Exception:
                pass
        log.info("WS closed for session %s", session_id)
        try:
            await websocket.close()
        except Exception:
            pass
