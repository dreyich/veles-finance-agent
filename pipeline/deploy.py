"""Step 4 — Deploy new adapter to HuggingFace.

Pushes the trained adapter to HF Hub under HF_REPO_ID.
Only runs if eval passed. Tags the release with the version string.
Updates the model card with the new training stats.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import structlog

from pipeline.config import AUTO_DEPLOY, HF_REPO_ID, HF_TOKEN, REPORTS_DIR

logger = structlog.get_logger(__name__)


def deploy(
    adapter_path: str,
    version: str,
    eval_report: dict,
    force: bool = False,
) -> bool:
    """Push adapter to HuggingFace Hub.

    Args:
        adapter_path: Local path to the trained adapter.
        version: Version string (e.g. "v2-202607").
        eval_report: Dict from eval.py — must have passed=True.
        force: Skip AUTO_DEPLOY check (for manual deploys).

    Returns:
        True if deployed successfully.
    """
    if not force and not AUTO_DEPLOY:
        logger.info("deploy_skipped", reason="AUTO_DEPLOY=false — run with --force to deploy manually")
        print("AUTO_DEPLOY=false. To deploy manually: python -m pipeline.deploy --force ...")
        return False

    if not eval_report.get("passed"):
        logger.error("deploy_blocked", reason="eval did not pass — refusing to deploy")
        print("Eval FAILED — deployment blocked.")
        return False

    if not HF_TOKEN:
        logger.error("deploy_no_token", hint="Set HF_TOKEN environment variable")
        sys.exit(1)

    try:
        from huggingface_hub import HfApi
    except ImportError:
        logger.error("deploy_missing_deps", hint="pip install huggingface_hub")
        sys.exit(1)

    api = HfApi(token=HF_TOKEN)
    metrics = eval_report.get("metrics", {})

    logger.info(
        "deploy_start",
        repo=HF_REPO_ID,
        version=version,
        adapter=adapter_path,
    )

    # Upload adapter files
    api.upload_folder(
        folder_path=adapter_path,
        repo_id=HF_REPO_ID,
        repo_type="model",
        commit_message=f"Release {version} — verdict_rate={metrics.get('verdict_rate', '?')}",
        ignore_patterns=["checkpoints/*", "*.log"],
    )

    # Create a git tag for this version
    try:
        api.create_tag(
            repo_id=HF_REPO_ID,
            repo_type="model",
            tag=version,
            message=f"Auto-release {version} from closed learning loop pipeline",
        )
        logger.info("deploy_tag_created", tag=version)
    except Exception as exc:
        # Tag already exists — not fatal
        logger.warning("deploy_tag_skipped", error=str(exc))

    # Save deploy record
    record = {
        "version": version,
        "repo_id": HF_REPO_ID,
        "adapter_path": adapter_path,
        "metrics": metrics,
        "deployed_at": datetime.now(timezone.utc).isoformat(),
    }
    out_dir = Path(REPORTS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"deploy_{version}.json").write_text(json.dumps(record, indent=2))

    logger.info(
        "deploy_complete",
        repo=HF_REPO_ID,
        version=version,
        verdict_rate=metrics.get("verdict_rate"),
    )
    print(f"Deployed {version} to https://huggingface.co/{HF_REPO_ID}")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--eval-report", required=True, help="Path to eval_report.json")
    parser.add_argument("--force", action="store_true", help="Deploy even if AUTO_DEPLOY=false")
    args = parser.parse_args()

    with open(args.eval_report) as f:
        eval_report = json.load(f)

    ok = deploy(args.adapter, args.version, eval_report, force=args.force)
    sys.exit(0 if ok else 1)
