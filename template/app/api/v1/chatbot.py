"""Chatbot API endpoints for handling chat interactions.

This module provides endpoints for chat interactions, including regular chat,
streaming chat, message history management, and chat history clearing.
"""

import asyncio
import json
import time

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
)
from fastapi.responses import StreamingResponse

from app.api.v1.auth import get_current_session
from app.core.config import settings
from app.core.langgraph.graph import LangGraphAgent
from app.core.limiter import limiter
from app.core.logging import logger
from app.core.metrics import llm_stream_duration_seconds
from app.domain.job_status import AsyncJobRequest, AsyncJobResponse, JobStatus
from app.infrastructure.job_store import job_store
from app.models.session import Session
from app.schemas import Message
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    StreamResponse,
)
from app.schemas.dd_report import AnalyzeRequest, DDReport
from app.services.session_naming import maybe_name_session

router = APIRouter()
agent = LangGraphAgent()


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chat"][0])
async def chat(
    request: Request,
    chat_request: ChatRequest,
    session: Session = Depends(get_current_session),
):
    """Process a chat request using LangGraph.

    Args:
        request: The FastAPI request object for rate limiting.
        chat_request: The chat request containing messages.
        session: The current session from the auth token.

    Returns:
        ChatResponse: The processed chat response.

    Raises:
        HTTPException: If there's an error processing the request.
    """
    try:
        logger.info(
            "chat_request_received",
            session_id=session.id,
            message_count=len(chat_request.messages),
        )

        if settings.SESSION_NAMING_ENABLED:
            maybe_name_session(session.id, session.name, chat_request.messages)

        result = await agent.get_response(
            chat_request.messages, session.id, user_id=str(session.user_id), username=session.username
        )

        logger.info("chat_request_processed", session_id=session.id)

        return ChatResponse(messages=result)
    except Exception as e:
        logger.exception("chat_request_failed", session_id=session.id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chat_stream"][0])
async def chat_stream(
    request: Request,
    chat_request: ChatRequest,
    session: Session = Depends(get_current_session),
):
    """Process a chat request using LangGraph with streaming response.

    Args:
        request: The FastAPI request object for rate limiting.
        chat_request: The chat request containing messages.
        session: The current session from the auth token.

    Returns:
        StreamingResponse: A streaming response of the chat completion.

    Raises:
        HTTPException: If there's an error processing the request.
    """
    try:
        logger.info(
            "stream_chat_request_received",
            session_id=session.id,
            message_count=len(chat_request.messages),
        )

        if settings.SESSION_NAMING_ENABLED:
            maybe_name_session(session.id, session.name, chat_request.messages)

        async def event_generator():
            """Generate streaming events.

            Yields:
                str: Server-sent events in JSON format.

            Raises:
                Exception: If there's an error during streaming.
            """
            try:
                with llm_stream_duration_seconds.labels(model=agent.llm_service.get_llm().get_name()).time():
                    async for chunk in agent.get_stream_response(
                        chat_request.messages, session.id, user_id=str(session.user_id), username=session.username
                    ):
                        response = StreamResponse(content=chunk, done=False)
                        yield f"data: {json.dumps(response.model_dump(mode='json'))}\n\n"

                # Send final message indicating completion
                final_response = StreamResponse(content="", done=True)
                yield f"data: {json.dumps(final_response.model_dump(mode='json'))}\n\n"

            except Exception as e:
                logger.exception(
                    "stream_chat_request_failed",
                    session_id=session.id,
                    error=str(e),
                )
                error_response = StreamResponse(content=str(e), done=True)
                yield f"data: {json.dumps(error_response.model_dump(mode='json'))}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    except Exception as e:
        logger.exception(
            "stream_chat_request_failed",
            session_id=session.id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze", response_model=DDReport)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chat"][0])
async def analyze(
    request: Request,
    analyze_request: AnalyzeRequest,
    session: Session = Depends(get_current_session),
):
    """Run a structured Due Diligence analysis and return a machine-parseable DDReport.

    Unlike /chat which returns free-form text, this endpoint returns a typed
    JSON report (DDReport schema) with explicit APPROVED/REJECTED verdict,
    confidence score, and section-level breakdown.

    The agent first calls get_market_data to fetch live data, then reasons
    via FinCoT, and finally returns structured output validated against DDReport.
    """
    from datetime import date

    from app.core.langgraph.tools.market_data_tools import get_market_data
    from app.services.llm import llm_service

    ticker = analyze_request.ticker.upper().strip()
    risk_profile = analyze_request.risk_profile

    logger.info("analyze_request_received", ticker=ticker, risk_profile=risk_profile, session_id=session.id)

    try:
        # Step 1 — Fetch live market data deterministically
        market_snapshot = get_market_data.invoke({"ticker": ticker})

        # Step 2 — Build DD prompt
        dd_prompt = (
            f"Perform a full Due Diligence analysis for **{ticker}** "
            f"for a **{risk_profile}** risk profile investor.\n\n"
            f"Market data:\n{market_snapshot}\n\n"
            f"Return a complete DDReport JSON. Today is {date.today().isoformat()}."
        )

        # Step 3 — Call LLM with structured output (DDReport schema)
        report: DDReport = await llm_service.call(
            messages=[{"role": "user", "content": dd_prompt}],
            response_format=DDReport,
        )

        logger.info(
            "analyze_request_completed",
            ticker=ticker,
            verdict=report.verdict,
            confidence=report.confidence,
            session_id=session.id,
        )
        return report

    except Exception as e:
        logger.exception("analyze_request_failed", ticker=ticker, error=str(e), session_id=session.id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/messages", response_model=ChatResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["messages"][0])
async def get_session_messages(
    request: Request,
    session: Session = Depends(get_current_session),
):
    """Get all messages for a session.

    Args:
        request: The FastAPI request object for rate limiting.
        session: The current session from the auth token.

    Returns:
        ChatResponse: All messages in the session.

    Raises:
        HTTPException: If there's an error retrieving the messages.
    """
    try:
        messages = await agent.get_chat_history(session.id)
        return ChatResponse(messages=messages)
    except Exception as e:
        logger.exception("get_messages_failed", session_id=session.id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/messages")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["messages"][0])
async def clear_chat_history(
    request: Request,
    session: Session = Depends(get_current_session),
):
    """Clear all messages for a session.

    Args:
        request: The FastAPI request object for rate limiting.
        session: The current session from the auth token.

    Returns:
        dict: A message indicating the chat history was cleared.
    """
    try:
        await agent.clear_chat_history(session.id)
        return {"message": "Chat history cleared successfully"}
    except Exception as e:
        logger.exception("clear_chat_history_failed", session_id=session.id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── Phase 5.1 — Async Job Endpoints ──────────────────────────────────────────

@router.post("/chat/async", response_model=AsyncJobResponse, status_code=202)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chat"][0])
async def chat_async(
    request: Request,
    chat_request: ChatRequest,
    session: Session = Depends(get_current_session),
):
    """Submit a chat request for async processing.

    Returns immediately with a job_id (HTTP 202 Accepted).
    Poll GET /chatbot/jobs/{job_id} to retrieve the result when done.

    This endpoint is preferred for B2B integrations where the client
    cannot maintain a long-lived HTTP connection for streaming.
    """
    job_id = await job_store.create(
        session_id=session.id,
        user_id=str(session.user_id),
    )

    # Fire-and-forget: run LLM inference in background
    asyncio.create_task(
        _run_async_job(
            job_id=job_id,
            messages=chat_request.messages,
            session=session,
        )
    )

    logger.info("async_job_submitted", job_id=job_id, session_id=session.id)
    return AsyncJobResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        poll_url=f"{settings.API_V1_STR}/chatbot/jobs/{job_id}",
        estimated_seconds=20,
    )


async def _run_async_job(
    job_id: str,
    messages: list[Message],
    session: Session,
) -> None:
    """Background coroutine: run agent, update job status."""
    await job_store.set_running(job_id)
    start = time.monotonic()
    try:
        result_messages = await agent.get_response(
            messages=messages,
            session_id=session.id,
            user_id=str(session.user_id),
            username=session.username,
        )
        duration_ms = (time.monotonic() - start) * 1000

        # Serialize messages and extract envelope if available
        msg_dicts = [m.model_dump() for m in result_messages]
        envelope = None
        if result_messages:
            last = result_messages[-1]
            # Try to extract envelope JSON from assistant content
            from app.utils.graph import parse_envelope_from_response
            env = parse_envelope_from_response(last.content)
            if env:
                envelope = env.model_dump()

        await job_store.set_done(
            job_id=job_id,
            messages=msg_dicts,
            envelope=envelope,
            duration_ms=duration_ms,
        )
    except Exception as exc:
        logger.exception("async_job_failed", job_id=job_id, error=str(exc))
        await job_store.set_error(job_id=job_id, error=str(exc))


@router.get("/jobs/{job_id}")
@limiter.limit("60 per minute")
async def get_job_status(
    request: Request,
    job_id: str,
    session: Session = Depends(get_current_session),
):
    """Poll for async job result.

    Returns:
        200 + {status: "pending"|"running"} while in progress.
        200 + {status: "done", messages: [...], envelope: {...}} when complete.
        200 + {status: "error", error: "..."} on failure.
        404 if job_id is unknown or expired (TTL: 1 hour).
    """
    result = await job_store.get(job_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Job '{job_id}' not found or expired (TTL: 1 hour)",
        )
    return result
