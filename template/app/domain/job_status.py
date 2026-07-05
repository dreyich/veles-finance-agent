"""Async Job Domain Models — Phase 5.1.

Enables non-blocking LLM execution:
  1. POST /chatbot/chat/async  → returns {job_id, status: "pending"} instantly
  2. GET  /jobs/{job_id}       → client polls until status == "done" or "error"

Why not Celery?
  - Celery requires a worker process + broker + result backend + beat
  - FastAPI + asyncio handles concurrent LLM calls naturally
  - Valkey (Redis-compatible) is already running — we use it as the job store
  - For distributed worker scaling, Celery can replace JobStore later without
    changing the API contract (job_id, status enum, result schema stay the same)
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    PENDING = "pending"     # queued, not yet started
    RUNNING = "running"     # LLM inference in progress
    DONE = "done"           # completed successfully
    ERROR = "error"         # failed — see error field


class AsyncJobRequest(BaseModel):
    """Request body for POST /chatbot/chat/async."""

    messages: list[dict] = Field(
        ..., min_length=1, description="Conversation messages (OpenAI format)"
    )
    session_id: Optional[str] = Field(
        None, description="Existing session ID to continue; None creates a new session"
    )


class AsyncJobResponse(BaseModel):
    """Immediate response from POST /chatbot/chat/async."""

    job_id: str = Field(..., description="Unique job identifier for polling")
    status: JobStatus = Field(JobStatus.PENDING)
    poll_url: str = Field(..., description="URL to poll for result: GET /jobs/{job_id}")
    estimated_seconds: int = Field(
        20, description="Rough ETA in seconds (LLM-dependent)"
    )


class JobResult(BaseModel):
    """Full job record returned by GET /jobs/{job_id}."""

    job_id: str
    status: JobStatus
    created_at: str
    updated_at: str
    session_id: Optional[str] = None
    # Populated when status == done
    messages: Optional[list[dict]] = None
    envelope: Optional[dict] = None
    duration_ms: Optional[float] = None
    # Populated when status == error
    error: Optional[str] = None
