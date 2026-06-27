"""Closed Learning Loop — main orchestrator.

Runs the full pipeline: collect → train → eval → deploy.
Can be triggered manually or via cron/scheduler.

Usage:
    # Full run (collect, train, eval, deploy if passes)
    python -m pipeline.run_pipeline --version v2-202607

    # Check how much data is available
    python -m pipeline.run_pipeline --stats

    # Dry run (no training, no DB changes)
    python -m pipeline.run_pipeline --dry-run

    # Force deploy even if eval is borderline
    python -m pipeline.run_pipeline --force-deploy

Cron example (run on the 1st of every month at 2am):
    0 2 1 * * cd /app && python -m pipeline.run_pipeline --version v2-$(date +%%Y%%m)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import structlog

from pipeline.collect import collect, _stats
from pipeline.config import (
    ADAPTER_DIR,
    MIN_EXAMPLES_TO_TRAIN,
    MIN_QUALITY_SCORE,
    REPORTS_DIR,
)
from pipeline.deploy import deploy
from pipeline.eval import evaluate
from pipeline.train import train

logger = structlog.get_logger(__name__)


def run(
    version: str,
    dry_run: bool = False,
    force_deploy: bool = False,
    skip_deploy: bool = False,
) -> dict:
    """Run the full closed learning loop pipeline.

    Returns a summary dict with status of each step.
    """
    started_at = datetime.now(timezone.utc)
    summary = {
        "version": version,
        "started_at": started_at.isoformat(),
        "steps": {},
    }

    print(f"\n{'='*60}")
    print(f"  Veles Closed Learning Loop Pipeline")
    print(f"  Version: {version}")
    print(f"  Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print(f"{'='*60}\n")

    # ── Step 1: Collect ────────────────────────────────────────────────────────
    print("[1/4] Collecting training data...")
    dataset_path = collect(
        version=version,
        min_score=MIN_QUALITY_SCORE,
        min_examples=MIN_EXAMPLES_TO_TRAIN,
        dry_run=dry_run,
    )

    if dataset_path is None and not dry_run:
        summary["steps"]["collect"] = {"status": "skipped", "reason": "insufficient_examples"}
        summary["status"] = "aborted"
        _save_summary(summary)
        print(f"\nAborted: not enough high-quality examples (need {MIN_EXAMPLES_TO_TRAIN}).")
        print("Run `python -m pipeline.run_pipeline --stats` to see current data status.")
        return summary

    summary["steps"]["collect"] = {
        "status": "ok" if dataset_path else "dry_run",
        "dataset": str(dataset_path) if dataset_path else None,
    }
    print(f"   Dataset: {dataset_path or '(dry run)'}\n")

    # ── Step 2: Train ──────────────────────────────────────────────────────────
    print("[2/4] Training LoRA adapter...")
    adapter_path = train(
        dataset_path=str(dataset_path) if dataset_path else "dry_run",
        version=version,
        dry_run=dry_run,
    )

    summary["steps"]["train"] = {
        "status": "ok" if adapter_path else "dry_run",
        "adapter": str(adapter_path) if adapter_path else None,
    }
    print(f"   Adapter: {adapter_path or '(dry run)'}\n")

    # ── Step 3: Eval ───────────────────────────────────────────────────────────
    print("[3/4] Evaluating adapter...")
    eval_report = evaluate(
        adapter_path=str(adapter_path) if adapter_path else "dry_run",
        version=version,
        dry_run=dry_run,
    )

    summary["steps"]["eval"] = {
        "status": "passed" if eval_report["passed"] else "failed",
        "metrics": eval_report.get("metrics", {}),
    }

    metrics = eval_report.get("metrics", {})
    print(f"   verdict_rate:  {metrics.get('verdict_rate', '?')}")
    print(f"   thinking_rate: {metrics.get('thinking_rate', '?')}")
    print(f"   format_score:  {metrics.get('avg_format_score', '?')}")
    print(f"   Result: {'PASSED ✓' if eval_report['passed'] else 'FAILED ✗'}\n")

    if not eval_report["passed"] and not force_deploy:
        summary["status"] = "eval_failed"
        _save_summary(summary)
        print("Pipeline stopped: eval did not pass thresholds.")
        print("Fix the model or lower thresholds in config.py, then re-run.")
        return summary

    # ── Step 4: Deploy ─────────────────────────────────────────────────────────
    if skip_deploy:
        print("[4/4] Deploy skipped (--skip-deploy)\n")
        summary["steps"]["deploy"] = {"status": "skipped"}
    else:
        print("[4/4] Deploying to HuggingFace...")

        # Find eval report file
        reports_dir = Path(REPORTS_DIR)
        eval_reports = sorted(reports_dir.glob(f"eval_{version}_*.json"), reverse=True)
        eval_report_path = str(eval_reports[0]) if eval_reports else None

        deployed = deploy(
            adapter_path=str(adapter_path) if adapter_path else "dry_run",
            version=version,
            eval_report=eval_report,
            force=force_deploy,
        )
        summary["steps"]["deploy"] = {"status": "ok" if deployed else "skipped"}
        print()

    # ── Done ───────────────────────────────────────────────────────────────────
    summary["status"] = "complete"
    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
    summary["elapsed_seconds"] = round(elapsed)

    _save_summary(summary)

    print(f"{'='*60}")
    print(f"  Pipeline complete in {elapsed/60:.1f} minutes")
    print(f"  Version: {version}")
    print(f"{'='*60}\n")

    return summary


def _save_summary(summary: dict) -> None:
    out_dir = Path(REPORTS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"pipeline_{summary['version']}.json"
    path.write_text(json.dumps(summary, indent=2))
    logger.info("pipeline_summary_saved", path=str(path))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Veles closed learning loop pipeline")
    parser.add_argument(
        "--version",
        default=f"v2-{datetime.now(timezone.utc).strftime('%Y%m')}",
        help="Version tag for this training run (default: v2-YYYYMM)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Run without training or DB changes")
    parser.add_argument("--force-deploy", action="store_true", help="Deploy even if eval borderline")
    parser.add_argument("--skip-deploy", action="store_true", help="Train and eval but don't push to HF")
    parser.add_argument("--stats", action="store_true", help="Show data stats and exit")
    args = parser.parse_args()

    if args.stats:
        from pipeline.collect import _stats
        stats = _stats()
        print(json.dumps(stats, indent=2))
        needed = max(0, MIN_EXAMPLES_TO_TRAIN - stats["ready_for_training"])
        if needed > 0:
            print(f"\nNeed {needed} more high-quality conversations to trigger training.")
        else:
            print(f"\nReady to train! Run: python -m pipeline.run_pipeline --version {args.version}")
        sys.exit(0)

    result = run(
        version=args.version,
        dry_run=args.dry_run,
        force_deploy=args.force_deploy,
        skip_deploy=args.skip_deploy,
    )
    sys.exit(0 if result.get("status") in ("complete", "aborted") else 1)
