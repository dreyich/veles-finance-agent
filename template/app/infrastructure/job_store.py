"""Async Job Store — Phase 5.1.

Stores job state in Valkey/Redis (TTL=1h) with in-memory fallback.
The API contract (job_id, status, result) is identical regardless of backend,
so replacing this with a Celery result backend later is a one-file change.

TTL Strategy:
  - Jobs expire after 1 hour (enough for any polling client)
  - No persistence across server restart for in-memory fallback
  - Redis backend survives server restarts
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

import structlog

from app.domain.job_status import JobResult, JobStatus

logger = structlog.get_logger(__name__)

_JOB_TTL_SECONDS = 3600  # 1 hour


class _InMemoryJobStore:
    """Thread-safe in-memory fallback when Redis is unavailable."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict] = {}
        self._lock = asyncio.Lock()

    async def set(self, job_id: str, data: dict) -> None:
        async with self._lock:
            self._jobs[job_id] = {**data, "_expires_at": time.monotonic() + _JOB_TTL_SECONDS}

    async def get(self, job_id: str) -> Optional[dict]:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if time.monotonic() > job.get("_expires_at", float("inf")):
                del self._jobs[job_id]
                return None
            return {k: v for k, v in job.items() if k != "_expires_at"}


class JobStore:
    """Unified job store — Redis-first, in-memory fallback.

    Usage:
        store = JobStore()
        job_id = await store.create(session_id="...", user_id="...")
        await store.set_running(job_id)
        await store.set_done(job_id, messages=[...], envelope={...}, duration_ms=1234)
        result = await store.get(job_id)
    """

    def __init__(self) -> None:
        self._redis = None
        self._fallback = _InMemoryJobStore()
        self._redis_available = False

    async def initialize(self) -> None:
        """Try to connect to Redis/Valkey. Falls back silently if unavailable."""
        from app.core.config import settings
        if not settings.VALKEY_HOST:
            logger.info("job_store_using_memory_fallback", reason="VALKEY_HOST not set")
            return
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.Redis(
                host=settings.VALKEY_HOST,
                port=settings.VALKEY_PORT,
                db=settings.VALKEY_DB,
                decode_responses=True,
                socket_connect_timeout=2,
            )
            await self._redis.ping()
            self._redis_available = True
            logger.info("job_store_using_redis", host=settings.VALKEY_HOST)
        except Exception as exc:
            logger.warning("job_store_redis_unavailable", error=str(exc),
                          fallback="in_memory")
            self._redis = None

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    async def _set(self, job_id: str, data: dict) -> None:
        if self._redis_available and self._redis:
            try:
                await self._redis.setex(
                    f"job:{job_id}",
                    _JOB_TTL_SECONDS,
                    json.dumps(data, default=str),
                )
                return
            except Exception as exc:
                logger.warning("job_store_redis_write_failed", job_id=job_id, error=str(exc))
        await self._fallback.set(job_id, data)

    async def _get(self, job_id: str) -> Optional[dict]:
        if self._redis_available and self._redis:
            try:
                raw = await self._redis.get(f"job:{job_id}")
                if raw:
                    return json.loads(raw)
            except Exception as exc:
                logger.warning("job_store_redis_read_failed", job_id=job_id, error=str(exc))
        return await self._fallback.get(job_id)

    async def create(self, session_id: Optional[str], user_id: Optional[str]) -> str:
        """Create a new PENDING job. Returns job_id."""
        job_id = str(uuid4())
        now = self._now()
        await self._set(job_id, {
            "job_id": job_id,
            "status": JobStatus.PENDING.value,
            "created_at": now,
            "updated_at": now,
            "session_id": session_id,
            "user_id": user_id,
            "messages": None,
            "envelope": None,
            "duration_ms": None,
            "error": None,
        })
        logger.info("job_created", job_id=job_id, session_id=session_id)
        return job_id

    async def set_running(self, job_id: str) -> None:
        data = await self._get(job_id) or {}
        data.update(status=JobStatus.RUNNING.value, updated_at=self._now())
        await self._set(job_id, data)

    async def set_done(
        self,
        job_id: str,
        messages: list[dict],
        envelope: Optional[dict],
        duration_ms: float,
    ) -> None:
        data = await self._get(job_id) or {}
        data.update(
            status=JobStatus.DONE.value,
            updated_at=self._now(),
            messages=messages,
            envelope=envelope,
            duration_ms=round(duration_ms, 2),
        )
        await self._set(job_id, data)
        logger.info("job_done", job_id=job_id, duration_ms=round(duration_ms, 2))

    async def set_error(self, job_id: str, error: str) -> None:
        data = await self._get(job_id) or {}
        data.update(status=JobStatus.ERROR.value, updated_at=self._now(), error=error)
        await self._set(job_id, data)
        logger.error("job_failed", job_id=job_id, error=error)

    async def get(self, job_id: str) -> Optional[JobResult]:
        data = await self._get(job_id)
        if data is None:
            return None
        return JobResult(**{k: v for k, v in data.items() if k != "user_id"})


# Singleton — initialized once at app startup
job_store = JobStore()
