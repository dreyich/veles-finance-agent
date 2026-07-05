"""User feedback endpoint — thumbs up/down on agent responses.

Feedback updates quality_score in conversation_log, directly influencing
which examples get selected for the next training run.

POST /api/v1/feedback/
  { "session_id": "...", "message_index": 2, "rating": "good" | "bad", "note": "..." }
"""

from __future__ import annotations

from typing import Literal, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.v1.auth import get_current_session
from app.core.limiter import limiter
from app.core.config import settings
from app.models.database import async_engine
from app.models.session import Session

logger = structlog.get_logger(__name__)
router = APIRouter()

_RATING_DELTA = {
    "good": +0.20,
    "bad": -0.30,
}


class FeedbackRequest(BaseModel):
    session_id: str = Field(..., description="Session ID of the conversation being rated.")
    rating: Literal["good", "bad"] = Field(..., description="'good' (thumbs up) or 'bad' (thumbs down).")
    note: Optional[str] = Field(None, max_length=500, description="Optional text note from the user.")


class FeedbackResponse(BaseModel):
    status: str
    new_quality_score: Optional[float]
    message: str


@router.post("/", response_model=FeedbackResponse)
@limiter.limit("30 per minute")
async def submit_feedback(
    request: Request,
    body: FeedbackRequest,
    session: Session = Depends(get_current_session),
) -> FeedbackResponse:
    """Submit a thumbs-up or thumbs-down on the last agent response.

    Adjusts quality_score in conversation_log:
      good → +0.20 (capped at 1.0)
      bad  → -0.30 (floored at 0.0)

    High-quality examples (score ≥ 0.70) are selected for the next
    training run. Bad feedback can demote an example below the threshold.
    """
    if body.session_id != session.id:
        raise HTTPException(status_code=403, detail="Cannot rate another session.")

    delta = _RATING_DELTA[body.rating]

    try:
        async with async_engine.begin() as conn:
            # Find the most recent conversation entry for this session
            # that hasn't been demoted already
            result = await conn.execute(
                text("""
                    SELECT id, quality_score
                    FROM conversation_log
                    WHERE session_id = :sid
                      AND used_for_training = FALSE
                    ORDER BY created_at DESC
                    LIMIT 1
                """),
                {"sid": body.session_id},
            )
            row = result.fetchone()

            if not row:
                return FeedbackResponse(
                    status="no_op",
                    new_quality_score=None,
                    message="No unrated conversation found for this session.",
                )

            log_id, current_score = row
            new_score = round(min(1.0, max(0.0, (current_score or 0.5) + delta)), 3)

            await conn.execute(
                text("""
                    UPDATE conversation_log
                    SET quality_score = :score,
                        tool_calls = COALESCE(
                            (tool_calls::jsonb || :meta::jsonb)::text,
                            tool_calls
                        )
                    WHERE id = :id
                """),
                {
                    "score": new_score,
                    "id": log_id,
                    "meta": f'{{"user_feedback": "{body.rating}", "note": {repr(body.note)}}}',
                },
            )

        logger.info(
            "feedback_received",
            session_id=body.session_id,
            rating=body.rating,
            old_score=current_score,
            new_score=new_score,
            log_id=log_id,
        )

        msg = (
            "Thanks! This response will be prioritised for training."
            if body.rating == "good"
            else "Thanks! This response will be de-prioritised from training."
        )
        return FeedbackResponse(status="ok", new_quality_score=new_score, message=msg)

    except Exception as exc:
        logger.exception("feedback_failed", error=str(exc), session_id=body.session_id)
        raise HTTPException(status_code=500, detail="Failed to save feedback.")
