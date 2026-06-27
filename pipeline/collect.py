"""Step 1 — Collect high-quality training examples from PostgreSQL.

Queries conversation_log for examples not yet used for training,
filters by quality_score threshold, and exports to JSONL.
Marks exported rows as used_for_training to prevent re-use.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import structlog

from pipeline.config import (
    DATABASE_URL,
    DATASET_DIR,
    MAX_EXAMPLES_PER_RUN,
    MIN_EXAMPLES_TO_TRAIN,
    MIN_QUALITY_SCORE,
)

logger = structlog.get_logger(__name__)


def collect(
    version: str,
    min_score: float = MIN_QUALITY_SCORE,
    min_examples: int = MIN_EXAMPLES_TO_TRAIN,
    max_examples: int = MAX_EXAMPLES_PER_RUN,
    dry_run: bool = False,
) -> Path | None:
    """Collect training examples from the database.

    Args:
        version: Training version tag (e.g. "v2-2026-07").
        min_score: Minimum quality_score to include.
        min_examples: Abort if fewer than this many examples are available.
        max_examples: Cap on how many examples to collect per run.
        dry_run: If True, query and report but don't write or mark rows.

    Returns:
        Path to the output JSONL file, or None if not enough examples.
    """
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            # Count available high-quality examples
            cur.execute("""
                SELECT COUNT(*)
                FROM conversation_log
                WHERE used_for_training = FALSE
                  AND quality_score >= %s
            """, (min_score,))
            available = cur.fetchone()[0]

        logger.info("collect_available", available=available, min_required=min_examples)

        if available < min_examples:
            logger.warning(
                "collect_insufficient_examples",
                available=available,
                required=min_examples,
                hint=f"Need {min_examples - available} more high-quality conversations.",
            )
            return None

        if dry_run:
            logger.info("collect_dry_run", would_collect=min(available, max_examples))
            return None

        # Fetch examples ordered by quality (best first)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, user_message, assistant_response, tool_calls,
                       quality_score, has_thinking_tags, has_verdict
                FROM conversation_log
                WHERE used_for_training = FALSE
                  AND quality_score >= %s
                ORDER BY quality_score DESC, created_at ASC
                LIMIT %s
            """, (min_score, max_examples))
            rows = cur.fetchall()

        examples = []
        ids = []
        for row in rows:
            ex_id, user_msg, assistant_resp, tool_calls_json, score, has_thinking, has_verdict = row
            ids.append(ex_id)

            # Format as ChatML for Qwen/Unsloth training
            example = {
                "conversations": [
                    {"from": "human", "value": user_msg},
                    {"from": "gpt", "value": assistant_resp},
                ],
                "metadata": {
                    "quality_score": score,
                    "has_thinking_tags": has_thinking,
                    "has_verdict": has_verdict,
                    "training_version": version,
                },
            }
            examples.append(example)

        # Write JSONL dataset
        out_dir = Path(DATASET_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"train_{version}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.jsonl"

        with open(out_path, "w", encoding="utf-8") as f:
            for ex in examples:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")

        # Mark rows as used
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE conversation_log
                SET used_for_training = TRUE, training_version = %s
                WHERE id = ANY(%s)
            """, (version, ids))
        conn.commit()

        # Stats breakdown
        verdict_count = sum(1 for ex in examples if ex["metadata"]["has_verdict"])
        thinking_count = sum(1 for ex in examples if ex["metadata"]["has_thinking_tags"])
        avg_score = sum(ex["metadata"]["quality_score"] for ex in examples) / len(examples)

        logger.info(
            "collect_complete",
            total=len(examples),
            with_verdict=verdict_count,
            with_thinking=thinking_count,
            avg_quality=round(avg_score, 3),
            output=str(out_path),
            version=version,
        )
        return out_path

    finally:
        conn.close()


def _stats(min_score: float = MIN_QUALITY_SCORE) -> dict:
    """Return stats about available training data without collecting."""
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE used_for_training = FALSE) as unused,
                    COUNT(*) FILTER (WHERE used_for_training = FALSE AND quality_score >= %s) as ready,
                    ROUND(AVG(quality_score)::numeric, 3) as avg_score,
                    COUNT(*) FILTER (WHERE has_verdict = TRUE) as with_verdict,
                    COUNT(*) FILTER (WHERE has_thinking_tags = TRUE) as with_thinking
                FROM conversation_log
            """, (min_score,))
            row = cur.fetchone()
            return {
                "total_logged": row[0],
                "unused": row[1],
                "ready_for_training": row[2],
                "avg_quality_score": float(row[3] or 0),
                "with_verdict": row[4],
                "with_thinking": row[5],
                "min_score_threshold": min_score,
                "needed_to_trigger": MIN_EXAMPLES_TO_TRAIN,
            }
    finally:
        conn.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Collect training data from conversation_log")
    parser.add_argument("--version", default=f"v2-{datetime.now(timezone.utc).strftime('%Y%m')}")
    parser.add_argument("--min-score", type=float, default=MIN_QUALITY_SCORE)
    parser.add_argument("--min-examples", type=int, default=MIN_EXAMPLES_TO_TRAIN)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--stats", action="store_true", help="Show stats only")
    args = parser.parse_args()

    if args.stats:
        stats = _stats(args.min_score)
        print(json.dumps(stats, indent=2))
        sys.exit(0)

    result = collect(
        version=args.version,
        min_score=args.min_score,
        min_examples=args.min_examples,
        dry_run=args.dry_run,
    )
    if result:
        print(f"Dataset written to: {result}")
    else:
        print("Not enough examples or dry run — no dataset written.")
        sys.exit(1)
