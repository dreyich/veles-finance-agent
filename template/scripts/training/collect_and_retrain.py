"""Closed Learning Loop — Collect real conversations and trigger retraining.

This script is the heart of the continuous improvement pipeline:

  1. COLLECT  — Query conversation_log for high-quality turns not yet used
  2. CONVERT  — Transform them into FinCoT training pairs (JSONL)
  3. MERGE    — Combine with synthetic DD data for anti-forgetting
  4. RETRAIN  — Run Unsloth LoRA fine-tuning on the merged dataset
  5. MARK     — Flag used conversations in DB so they aren't reused

Usage:
    # Dry run — show stats without training
    python scripts/training/collect_and_retrain.py --dry-run

    # Full run (requires GPU)
    python scripts/training/collect_and_retrain.py --version v2

    # Custom quality threshold and minimum samples
    python scripts/training/collect_and_retrain.py --version v2 --min-score 0.6 --min-samples 50

Environment:
    DATABASE_URL    PostgreSQL connection string
    OPENAI_API_KEY  For OpenRouter (anti-forgetting data generation)
    HF_TOKEN        For pushing model to HuggingFace Hub
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_MIN_SCORE = 0.55       # Minimum quality_score to include in training
DEFAULT_MIN_SAMPLES = 30       # Abort if fewer real samples than this
DEFAULT_SYNTHETIC_RATIO = 0.3  # Fraction of synthetic data mixed in (anti-forgetting)
DEFAULT_EPOCHS = 2             # Fewer epochs for incremental fine-tuning
HF_REPO_TEMPLATE = "YOUR_HF_USERNAME/Finance-DD-{version}"

SYNTHETIC_DATA_PATH = Path("scripts/training/finance_qa_dd.jsonl")
OUTPUT_DIR = Path("outputs")


# ── Database helpers ──────────────────────────────────────────────────────────

def _get_db_url() -> str:
    url = os.getenv("DATABASE_URL", "")
    if not url:
        # Build from individual settings (mirrors app/core/config.py)
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5432")
        db = os.getenv("POSTGRES_DB", "food_order_db")
        user = os.getenv("POSTGRES_USER", "postgres")
        pwd = os.getenv("POSTGRES_PASSWORD", "postgres")
        url = f"postgresql://{user}:{pwd}@{host}:{port}/{db}"
    return url


def collect_conversations(min_score: float, limit: int = 5000) -> list[dict]:
    """Query conversation_log for high-quality unused turns."""
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        print("[ERR] psycopg2 not installed. Run: pip install psycopg2-binary")
        sys.exit(1)

    conn = psycopg2.connect(_get_db_url())
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, session_id, user_message, assistant_response,
                       tool_calls, quality_score, has_thinking_tags, has_verdict
                FROM conversation_log
                WHERE used_for_training = false
                  AND quality_score >= %s
                  AND response_length >= 100
                ORDER BY quality_score DESC, created_at DESC
                LIMIT %s
            """, (min_score, limit))
            rows = cur.fetchall()
            return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_as_used(ids: list[str], version: str) -> None:
    """Mark conversation IDs as used for training."""
    try:
        import psycopg2
    except ImportError:
        return

    conn = psycopg2.connect(_get_db_url())
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE conversation_log
                SET used_for_training = true,
                    training_version = %s
                WHERE id = ANY(%s)
            """, (version, ids))
        conn.commit()
        print(f"  Marked {len(ids)} conversations as used (version={version})")
    finally:
        conn.close()


# ── Conversion ────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an institutional Due Diligence Analyst. Given market data and a user's risk profile, provide a structured analysis using FinCoT methodology:

<thinking>
Step 1 - Valuation: compare P/E to sector average.
Step 2 - Stability: assess market cap and dividend.
Step 3 - News sentiment: bullish, bearish, or neutral.
Step 4 - Profile fit: Conservative/Moderate/Aggressive suitability.
Step 5 - Synthesise verdict.
</thinking>

<output>
## Due Diligence Report
**Valuation:** ...
**Financial Health:** ...
**News Sentiment:** ...
VERDICT: APPROVED ✓ — reason  OR  REJECTED ✗ — reason
</output>"""


def conversations_to_jsonl(rows: list[dict]) -> list[dict]:
    """Convert raw DB rows to FinCoT training pairs."""
    pairs = []
    for row in rows:
        response = row["assistant_response"]

        # Only include responses that already follow FinCoT format
        if not row["has_thinking_tags"] and "<thinking>" not in response:
            continue

        pairs.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": row["user_message"]},
                {"role": "assistant", "content": response},
            ],
            "metadata": {
                "type": "real_conversation",
                "session_id": row["session_id"],
                "quality_score": row["quality_score"],
                "has_verdict": row["has_verdict"],
                "source": "production",
            },
        })
    return pairs


def load_synthetic(path: Path, n: int) -> list[dict]:
    """Load N synthetic samples for anti-forgetting mixing."""
    if not path.exists():
        print(f"  [WARN] Synthetic data not found at {path} — skipping anti-forgetting mix")
        return []
    samples = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    samples.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    import random
    random.shuffle(samples)
    return samples[:n]


def write_merged_dataset(real: list[dict], synthetic: list[dict], output_path: Path) -> int:
    """Write merged dataset to JSONL. Returns total count."""
    import random
    merged = real + synthetic
    random.shuffle(merged)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for item in merged:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return len(merged)


# ── Stats ─────────────────────────────────────────────────────────────────────

def print_stats(rows: list[dict]) -> None:
    if not rows:
        print("  No qualifying conversations found.")
        return

    scores = [r["quality_score"] for r in rows]
    with_thinking = sum(1 for r in rows if r["has_thinking_tags"])
    with_verdict = sum(1 for r in rows if r["has_verdict"])

    print(f"  Total qualifying: {len(rows)}")
    print(f"  Avg quality score: {sum(scores)/len(scores):.3f}")
    print(f"  Min / Max score:   {min(scores):.3f} / {max(scores):.3f}")
    print(f"  Has <thinking>:    {with_thinking} ({with_thinking/len(rows)*100:.0f}%)")
    print(f"  Has verdict:       {with_verdict} ({with_verdict/len(rows)*100:.0f}%)")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Finance DD — Closed Learning Loop")
    parser.add_argument("--version", default="v2", help="Model version tag (e.g. v2, v3)")
    parser.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE)
    parser.add_argument("--min-samples", type=int, default=DEFAULT_MIN_SAMPLES)
    parser.add_argument("--synthetic-ratio", type=float, default=DEFAULT_SYNTHETIC_RATIO)
    parser.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS)
    parser.add_argument("--dry-run", action="store_true", help="Show stats only, no training")
    parser.add_argument("--push-to-hub", action="store_true", help="Push adapter to HuggingFace after training")
    args = parser.parse_args()

    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  Finance DD — Closed Learning Loop")
    print(f"  Version: {args.version}  |  Min score: {args.min_score}")
    print(f"{sep}\n")

    # ── Step 1: Collect ───────────────────────────────────────────────────────
    print("Step 1 — Collecting high-quality conversations from DB...")
    rows = collect_conversations(min_score=args.min_score)
    print_stats(rows)

    if len(rows) < args.min_samples:
        print(f"\n[ABORT] Only {len(rows)} qualifying conversations found.")
        print(f"        Need at least {args.min_samples} to retrain.")
        print(f"        Collect more user interactions and try again.")
        if not args.dry_run:
            sys.exit(0)
        return

    if args.dry_run:
        print(f"\n[DRY RUN] Would train on {len(rows)} real + synthetic samples.")
        print("          Run without --dry-run to start actual training.")
        return

    # ── Step 2: Convert ───────────────────────────────────────────────────────
    print(f"\nStep 2 — Converting {len(rows)} conversations to training pairs...")
    real_pairs = conversations_to_jsonl(rows)
    print(f"  Converted: {len(real_pairs)} valid FinCoT pairs")

    # ── Step 3: Merge with synthetic ──────────────────────────────────────────
    n_synthetic = int(len(real_pairs) * args.synthetic_ratio)
    print(f"\nStep 3 — Mixing in {n_synthetic} synthetic samples (anti-forgetting)...")
    synthetic = load_synthetic(SYNTHETIC_DATA_PATH, n_synthetic)
    print(f"  Synthetic loaded: {len(synthetic)}")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    dataset_path = OUTPUT_DIR / f"training_data_{args.version}_{timestamp}.jsonl"
    total = write_merged_dataset(real_pairs, synthetic, dataset_path)
    print(f"  Merged dataset: {total} pairs → {dataset_path}")

    # ── Step 4: Retrain ───────────────────────────────────────────────────────
    print(f"\nStep 4 — Starting Unsloth retraining (version={args.version})...")
    output_path = OUTPUT_DIR / f"finance-dd-{args.version}"
    cmd = [
        sys.executable,
        "scripts/training/train.py",
        "--data", str(dataset_path),
        "--output", str(output_path),
        "--epochs", str(args.epochs),
    ]
    if args.push_to_hub:
        hf_repo = HF_REPO_TEMPLATE.format(version=args.version)
        cmd += ["--push_to_hub", hf_repo]

    print(f"  Command: {' '.join(cmd)}\n")
    result = subprocess.run(cmd)

    if result.returncode != 0:
        print(f"\n[ERR] Training failed (exit code {result.returncode})")
        sys.exit(1)

    # ── Step 5: Mark as used ─────────────────────────────────────────────────
    print(f"\nStep 5 — Marking {len(rows)} conversations as used...")
    mark_as_used([r["id"] for r in rows], version=args.version)

    print(f"\n{sep}")
    print(f"  Done! Finance-DD-{args.version} trained successfully.")
    print(f"  Dataset:  {dataset_path}")
    print(f"  Adapter:  {output_path}/lora_adapter")
    if args.push_to_hub:
        print(f"  HF Hub:   https://huggingface.co/{HF_REPO_TEMPLATE.format(version=args.version)}")
    print(f"{sep}\n")


if __name__ == "__main__":
    main()
