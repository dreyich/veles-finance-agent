"""EpisodicStore — SQLite + FTS5 episodic memory layer (Phase 4.2).

Complements pgvector (semantic search) with fast keyword-based FTS.
Each "episode" is a structured summary of one conversation session.

Design decisions:
  - SQLite: zero-config, survives container restarts via Docker volume
  - FTS5: built into Python's stdlib sqlite3, no extra deps
  - Async-friendly: all writes use asyncio.to_thread (non-blocking)
  - 2200-char cap on summaries: prevents context bloat in system prompt

Schema:
  episodes        — structured episode data
  episodes_fts    — FTS5 virtual table mirroring episodes.summary
  user_memory     — per-user compressed memory file (capped at 2200 chars)
"""

import asyncio
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

_DB_PATH = Path("/app/logs/episodic_memory.db")
_MEMORY_DIR = Path("/app/logs/users")
_MAX_MEMORY_CHARS = 2200


def _get_connection() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _init_schema() -> None:
    """Create tables if they don't exist. Idempotent — safe to call on every startup."""
    with _get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS episodes (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id    TEXT    NOT NULL,
                user_id       TEXT,
                created_at    TEXT    NOT NULL,
                summary       TEXT    NOT NULL,
                intent_counts TEXT,
                tickers       TEXT,
                turn_count    INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_episodes_user
                ON episodes (user_id, created_at DESC);

            CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts
                USING fts5(
                    summary,
                    tickers,
                    content=episodes,
                    content_rowid=id
                );

            CREATE TABLE IF NOT EXISTS user_memory (
                user_id    TEXT PRIMARY KEY,
                content    TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                char_count INTEGER DEFAULT 0
            );
        """)


# ── Public async API ──────────────────────────────────────────────────────────

async def write_episode(
    session_id: str,
    user_id: Optional[str],
    messages: list[dict],
    envelopes: list,
) -> None:
    """Write a session episode to the store. Non-blocking (uses asyncio.to_thread)."""
    await asyncio.to_thread(_write_episode_sync, session_id, user_id, messages, envelopes)


async def search_episodes(
    query: str,
    user_id: Optional[str] = None,
    limit: int = 5,
) -> list[dict]:
    """FTS search across episode summaries. Non-blocking."""
    return await asyncio.to_thread(_search_sync, query, user_id, limit)


async def get_user_memory(user_id: str) -> str:
    """Return the compressed memory string for a user (max 2200 chars)."""
    return await asyncio.to_thread(_get_user_memory_sync, user_id)


async def update_user_memory(user_id: str, new_facts: str) -> None:
    """Append facts to user memory, compacting if > 2200 chars. Non-blocking."""
    await asyncio.to_thread(_update_user_memory_sync, user_id, new_facts)


# ── Sync helpers (run in thread pool) ────────────────────────────────────────

def _write_episode_sync(
    session_id: str,
    user_id: Optional[str],
    messages: list[dict],
    envelopes: list,
) -> None:
    summary = _build_summary(messages, envelopes)
    intent_counts = _count_intents(envelopes)
    tickers = _extract_tickers(envelopes)
    now = datetime.now(timezone.utc).isoformat()

    try:
        with _get_connection() as conn:
            cur = conn.execute(
                """INSERT INTO episodes
                   (session_id, user_id, created_at, summary, intent_counts, tickers, turn_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (session_id, user_id, now, summary,
                 json.dumps(intent_counts), json.dumps(tickers), len(messages)),
            )
            rowid = cur.lastrowid
            conn.execute(
                "INSERT INTO episodes_fts (rowid, summary, tickers) VALUES (?, ?, ?)",
                (rowid, summary, " ".join(tickers)),
            )
        logger.info("episode_written", session_id=session_id, user_id=user_id,
                    chars=len(summary), tickers=tickers)

        # Auto-update user memory with new facts
        if user_id and summary:
            _update_user_memory_sync(user_id, summary)

    except Exception as exc:
        logger.error("episode_write_failed", session_id=session_id, error=str(exc))


def _search_sync(query: str, user_id: Optional[str], limit: int) -> list[dict]:
    try:
        with _get_connection() as conn:
            if user_id:
                rows = conn.execute(
                    """SELECT e.session_id, e.summary, e.created_at, e.tickers
                       FROM episodes e
                       JOIN episodes_fts fts ON fts.rowid = e.id
                       WHERE episodes_fts MATCH ? AND e.user_id = ?
                       ORDER BY rank LIMIT ?""",
                    (query, user_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT e.session_id, e.summary, e.created_at, e.tickers
                       FROM episodes e
                       JOIN episodes_fts fts ON fts.rowid = e.id
                       WHERE episodes_fts MATCH ?
                       ORDER BY rank LIMIT ?""",
                    (query, limit),
                ).fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        logger.warning("episode_search_failed", query=query, error=str(exc))
        return []


def _get_user_memory_sync(user_id: str) -> str:
    try:
        with _get_connection() as conn:
            row = conn.execute(
                "SELECT content FROM user_memory WHERE user_id = ?", (user_id,)
            ).fetchone()
            return row["content"] if row else ""
    except Exception as exc:
        logger.warning("user_memory_read_failed", user_id=user_id, error=str(exc))
        return ""


def _update_user_memory_sync(user_id: str, new_facts: str) -> None:
    existing = _get_user_memory_sync(user_id)
    combined = (existing + "\n" + new_facts).strip()

    # Compact: if over limit, keep the tail (most recent facts)
    if len(combined) > _MAX_MEMORY_CHARS:
        combined = combined[-_MAX_MEMORY_CHARS:]
        # Trim to start at a newline boundary
        nl = combined.find("\n")
        if nl > 0:
            combined = combined[nl:].strip()

    now = datetime.now(timezone.utc).isoformat()
    try:
        with _get_connection() as conn:
            conn.execute(
                """INSERT INTO user_memory (user_id, content, updated_at, char_count)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                       content = excluded.content,
                       updated_at = excluded.updated_at,
                       char_count = excluded.char_count""",
                (user_id, combined, now, len(combined)),
            )
        logger.debug("user_memory_updated", user_id=user_id, chars=len(combined))
    except Exception as exc:
        logger.error("user_memory_write_failed", user_id=user_id, error=str(exc))


# ── Summary builders ──────────────────────────────────────────────────────────

def _build_summary(messages: list[dict], envelopes: list) -> str:
    """Build a structured, capped-2200-char summary from a conversation."""
    parts: list[str] = []

    # User queries (first 5, max 120 chars each)
    user_queries = [m["content"][:120] for m in messages if m.get("role") == "user"][:5]
    if user_queries:
        parts.append("QUERIES: " + " | ".join(user_queries))

    # Key results from envelopes
    for env in envelopes[:4]:
        intent = getattr(env.intent, "value", str(env.intent)) if hasattr(env, "intent") else "?"
        text = getattr(env, "text_response", "")[:200]
        parts.append(f"[{intent.upper()}] {text}")

        fd = getattr(env, "financial_data", None)
        if fd:
            if getattr(fd, "currency_pair", None) and getattr(fd, "rate", None):
                forecast = f" → forecast {fd.rate_forecast}" if getattr(fd, "rate_forecast", None) else ""
                parts.append(f"  RATE: {fd.currency_pair}={fd.rate}{forecast}")
            if getattr(fd, "ticker", None) and getattr(fd, "price", None):
                verdict = f" [{fd.verdict}]" if getattr(fd, "verdict", None) else ""
                parts.append(f"  EQUITY: {fd.ticker}=${fd.price}{verdict}")

    summary = "\n".join(parts)
    return summary[:_MAX_MEMORY_CHARS]


def _count_intents(envelopes: list) -> dict[str, int]:
    counts: dict[str, int] = {}
    for env in envelopes:
        if hasattr(env, "intent"):
            k = getattr(env.intent, "value", str(env.intent))
            counts[k] = counts.get(k, 0) + 1
    return counts


def _extract_tickers(envelopes: list) -> list[str]:
    tickers: set[str] = set()
    for env in envelopes:
        fd = getattr(env, "financial_data", None)
        if fd:
            if getattr(fd, "ticker", None):
                tickers.add(fd.ticker)
            if getattr(fd, "currency_pair", None):
                tickers.add(fd.currency_pair)
    return sorted(tickers)


# ── Startup init ──────────────────────────────────────────────────────────────

def init_episodic_store() -> None:
    """Call once at application startup to create DB schema."""
    try:
        _init_schema()
        logger.info("episodic_store_initialized", db_path=str(_DB_PATH))
    except Exception as exc:
        logger.error("episodic_store_init_failed", error=str(exc))
