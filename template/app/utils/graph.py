"""This file contains the graph utilities for the application."""

import json
import re
import tiktoken
from typing import Optional

from langchain_core.messages import BaseMessage
from langchain_core.messages import trim_messages as _trim_messages

from app.core.config import settings
from app.core.logging import logger
from app.schemas import Message
from app.schemas.envelope import FinancialData, IntentEnum, UniversalEnvelope

# Cache tiktoken encoding at module level — thread-safe and reusable
try:
    _TIKTOKEN_ENCODING = tiktoken.encoding_for_model(settings.DEFAULT_LLM_MODEL)
except KeyError:
    _TIKTOKEN_ENCODING = tiktoken.get_encoding("cl100k_base")


def _count_tokens_tiktoken(messages: list) -> int:
    """Count tokens locally using tiktoken — no API call needed."""
    num_tokens = 0
    for message in messages:
        # Every message has overhead tokens for role/name
        num_tokens += 4
        if isinstance(message, dict):
            for _, value in message.items():
                if isinstance(value, str):
                    num_tokens += len(_TIKTOKEN_ENCODING.encode(value))
        elif isinstance(message, BaseMessage):
            content = message.content
            if isinstance(content, str):
                num_tokens += len(_TIKTOKEN_ENCODING.encode(content))
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, str):
                        num_tokens += len(_TIKTOKEN_ENCODING.encode(block))
                    elif isinstance(block, dict) and "text" in block:
                        num_tokens += len(_TIKTOKEN_ENCODING.encode(block["text"]))
    num_tokens += 2  # every reply is primed with assistant
    return num_tokens


def dump_messages(messages: list[Message]) -> list[dict]:
    """Dump the messages to a list of dictionaries.

    Args:
        messages (list[Message]): The messages to dump.

    Returns:
        list[dict]: The dumped messages.
    """
    return [message.model_dump() for message in messages]


def extract_text_content(content: str | list) -> str:
    """Extract plain text from an LLM content value.

    Handles both the simple string format and the structured block list returned
    by GPT-5 / Responses API models:
        [{'type': 'reasoning', ...}, {'type': 'text', 'text': '...'}]

    Args:
        content: Raw content from a LangChain BaseMessage.

    Returns:
        Plain text string (empty string when nothing extractable is present).
    """
    if isinstance(content, str):
        return content

    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict):
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif block.get("type") == "reasoning":
                logger.debug(
                    "reasoning_block_received",
                    reasoning_id=block.get("id"),
                    has_summary=bool(block.get("summary")),
                )
    return "".join(parts)


def process_llm_response(response: BaseMessage) -> BaseMessage:
    """Normalise a raw LLM response so that ``response.content`` is always a plain string, regardless of the provider's content format.

    Args:
        response: The raw response from the LLM.

    Returns:
        The same BaseMessage instance with ``content`` set to a plain string.
    """
    if isinstance(response.content, list):
        response.content = extract_text_content(response.content)
        logger.debug(
            "processed_structured_content",
            content_block_count=len(response.content),
            extracted_length=len(response.content),
        )
    return response


def parse_envelope_from_response(content: str, strict: bool = False) -> Optional[UniversalEnvelope]:
    """Extract and validate a UniversalEnvelope from the LLM's raw text response.

    Tries extraction strategies in order:
    1. JSON inside <output>...</output> tags  (current FinCoT format)
    2. Raw JSON object starting with {        (guided-decoding format, Phase 1.2b)
    3. Fallback: build a 'chat' envelope from the raw text — skipped when
       ``strict=True``.

    Args:
        strict: When True, return None instead of falling back to strategy 3.
            Use this for the graph's routing decision (_chat), so a model that
            misses the <output> block is routed to _finalize for guaranteed
            constrained decoding instead of silently masking the format
            failure behind a low-fidelity 'chat' envelope. Leave False for
            display/formatting call sites (chat history, API response
            serialization) where losing the response entirely would be worse
            than showing it unstructured.

    Returns a validated UniversalEnvelope on success. Returns None if
    non-strict fallback itself fails (should never happen for non-empty
    content), or always when strict=True and strategies 1/2 didn't match.
    """
    if not content or not content.strip():
        return None

    raw = content.strip()

    # ── Strategy 1: extract from <output>…</output> ───────────────────────
    out_match = re.search(r"<output>([\s\S]*?)</output>", raw, re.IGNORECASE)
    json_candidate = out_match.group(1).strip() if out_match else None

    # ── Strategy 2: raw JSON (starts with '{') ────────────────────────────
    if json_candidate is None and raw.startswith("{"):
        json_candidate = raw

    # ── Try to parse and validate ─────────────────────────────────────────
    if json_candidate:
        try:
            data = json.loads(json_candidate)
            envelope = UniversalEnvelope.model_validate(data)
            logger.debug(
                "envelope_parsed",
                intent=envelope.intent,
                has_financial_data=envelope.financial_data is not None,
            )
            return envelope
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning(
                "envelope_parse_failed",
                strategy="json",
                error=str(exc),
                snippet=json_candidate[:120],
            )

    if strict:
        return None

    # ── Strategy 3: fallback — wrap plain text as 'chat' envelope ─────────
    # Strips <thinking>…</thinking> from the display text.
    display = re.sub(r"<thinking>[\s\S]*?</thinking>", "", raw, flags=re.IGNORECASE).strip()
    display = re.sub(r"</?output>", "", display, flags=re.IGNORECASE).strip()

    if not display:
        display = raw  # nothing stripped — use everything

    try:
        return UniversalEnvelope(
            intent=IntentEnum.CHAT,
            text_response=display[:4000],  # guard against absurdly long fallbacks
        )
    except Exception as exc:
        logger.error("envelope_fallback_failed", error=str(exc))
        return None


def prepare_messages(messages: list[Message], system_prompt: str) -> list[Message]:
    """Prepare the messages for the LLM.

    Args:
        messages (list[Message]): The messages to prepare.
        system_prompt (str): The system prompt to use.

    Returns:
        list[Message]: The prepared messages.
    """
    raw_dicts = dump_messages(messages)

    try:
        trimmed_messages = _trim_messages(
            raw_dicts,
            strategy="last",
            token_counter=_count_tokens_tiktoken,
            max_tokens=settings.MAX_TOKENS,
            start_on="human",
            include_system=False,
            allow_partial=False,
        )
    except ValueError as e:
        # Handle unrecognized content blocks (e.g., reasoning blocks from GPT-5)
        if "Unrecognized content block type" in str(e):
            logger.warning(
                "token_counting_failed_skipping_trim",
                error=str(e),
                message_count=len(messages),
            )
            trimmed_messages = raw_dicts
        else:
            raise

    # Guard: trim_messages returns empty when the conversation exceeds MAX_TOKENS
    # and start_on="human" cannot be satisfied. Without this guard, vLLM receives
    # only the system prompt → BadRequestError: "no first user message".
    if not trimmed_messages:
        last_user = next(
            (m for m in reversed(raw_dicts) if m.get("role") == "user"),
            None,
        )
        trimmed_messages = [last_user] if last_user else raw_dicts[-1:]
        logger.warning(
            "trim_messages_returned_empty_using_last_user",
            original_count=len(messages),
            max_tokens=settings.MAX_TOKENS,
        )

    return [Message(role="system", content=system_prompt)] + trimmed_messages
