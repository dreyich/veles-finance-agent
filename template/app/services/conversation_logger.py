"""Conversation logger for the closed learning loop.

Every agent response is saved to PostgreSQL with quality signals.
The collect_and_retrain.py script queries this table to build
training datasets for periodic model fine-tuning.

Quality signals computed at write time:
  has_thinking_tags  — response contains <thinking>...</thinking>
  has_verdict        — response contains APPROVED or REJECTED
  response_length    — character count of assistant response
  quality_score      — composite score (0.0–1.0) used for filtering
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import async_engine

logger = structlog.get_logger(__name__)


def _compute_quality_score(
    user_message: str,
    assistant_response: str,
    has_thinking_tags: bool,
    has_verdict: bool,
    duration_ms: Optional[float],
) -> float:
    """Score a conversation turn from 0.0 to 1.0 for training suitability.

    Higher score = better training example.
    Criteria (weighted):
      0.35 — has <thinking> tags (FinCoT format followed)
      0.25 — has APPROVED/REJECTED verdict (DD task completed)
      0.20 — response length >= 300 chars (substantive answer)
      0.10 — user message mentions a ticker or financial term
      0.10 — response time reasonable (< 30s = not timeout/retry)
    """
    score = 0.0

    if has_thinking_tags:
        score += 0.35
    if has_verdict:
        score += 0.25
    if len(assistant_response) >= 300:
        score += 0.20

    financial_keywords = ["ticker", "p/e", "market cap", "nvda", "aapl", "msft",
                          "portfolio", "due diligence", "revenue", "earnings",
                          "dividend", "valuation", "approved", "rejected"]
    if any(kw in user_message.lower() for kw in financial_keywords):
        score += 0.10

    if duration_ms is not None and duration_ms < 30_000:
        score += 0.10

    return round(score, 3)


async def log_conversation(
    session_id: str,
    user_id: Optional[str],
    user_message: str,
    assistant_response: str,
    tool_calls: Optional[list[dict]],
    model: str,
    duration_ms: Optional[float] = None,
) -> None:
    """Persist one conversation turn to the conversation_log table.

    Fire-and-forget — called from graph.py as an asyncio.create_task().
    Failures are logged but never propagate to the user request.
    """
    try:
        has_thinking = "<thinking>" in assistant_response and "</thinking>" in assistant_response
        has_verdict = "APPROVED" in assistant_response.upper() or "REJECTED" in assistant_response.upper()
        quality = _compute_quality_score(
            user_message, assistant_response, has_thinking, has_verdict, duration_ms
        )

        record = {
            "id": str(uuid4()),
            "session_id": session_id,
            "user_id": user_id,
            "user_message": user_message,
            "assistant_response": assistant_response,
            "tool_calls": json.dumps(tool_calls or []),
            "model": model,
            "duration_ms": duration_ms,
            "has_thinking_tags": has_thinking,
            "has_verdict": has_verdict,
            "response_length": len(assistant_response),
            "quality_score": quality,
            "used_for_training": False,
            "training_version": None,
            "created_at": datetime.now(timezone.utc),
        }

        async with async_engine.begin() as conn:
            await conn.execute(
                text("""
                    INSERT INTO conversation_log (
                        id, session_id, user_id, user_message, assistant_response,
                        tool_calls, model, duration_ms, has_thinking_tags, has_verdict,
                        response_length, quality_score, used_for_training,
                        training_version, created_at
                    ) VALUES (
                        :id, :session_id, :user_id, :user_message, :assistant_response,
                        :tool_calls, :model, :duration_ms, :has_thinking_tags, :has_verdict,
                        :response_length, :quality_score, :used_for_training,
                        :training_version, :created_at
                    )
                """),
                record,
            )

        logger.info(
            "conversation_logged",
            session_id=session_id,
            quality_score=quality,
            has_thinking=has_thinking,
            has_verdict=has_verdict,
        )

    except Exception as exc:
        logger.error("conversation_log_failed", error=str(exc), session_id=session_id)
