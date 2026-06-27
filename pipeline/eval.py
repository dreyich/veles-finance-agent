"""Step 3 — Evaluate new adapter against held-out test cases.

Runs the new adapter on test_cases.jsonl and checks:
  - verdict_rate:  % of responses containing APPROVED/REJECTED
  - thinking_rate: % of responses with <thinking> tags
  - format_score:  % of responses following full FinCoT structure

Only passes if all metrics >= thresholds in config.py.
Produces an eval_report.json saved alongside the adapter.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import structlog

from pipeline.config import (
    EVAL_MIN_THINKING_RATE,
    EVAL_MIN_VERDICT_RATE,
    EVAL_TEST_CASES_PATH,
    MAX_SEQ_LENGTH,
    REPORTS_DIR,
)

logger = structlog.get_logger(__name__)


def _load_test_cases(path: str) -> list[dict]:
    cases = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def _score_response(response: str) -> dict:
    text = response.upper()
    has_verdict = "APPROVED" in text or "REJECTED" in text
    has_thinking = "<THINKING>" in text and "</THINKING>" in text
    has_output = "<OUTPUT>" in text and "</OUTPUT>" in text
    has_numbers = any(c.isdigit() for c in response)

    # FinCoT format score: thinking + output + verdict + numbers
    format_score = sum([has_thinking, has_output, has_verdict, has_numbers]) / 4.0

    return {
        "has_verdict": has_verdict,
        "has_thinking": has_thinking,
        "has_output_tags": has_output,
        "has_numbers": has_numbers,
        "format_score": round(format_score, 3),
        "response_length": len(response),
    }


def evaluate(
    adapter_path: str,
    version: str,
    test_cases_path: str = EVAL_TEST_CASES_PATH,
    dry_run: bool = False,
) -> dict:
    """Run eval against test cases. Returns report dict with pass/fail."""

    cases = _load_test_cases(test_cases_path)
    logger.info("eval_start", adapter=adapter_path, test_cases=len(cases), version=version)

    if dry_run:
        logger.info("eval_dry_run", test_cases=len(cases))
        return {"passed": True, "dry_run": True, "test_cases": len(cases)}

    try:
        from unsloth import FastLanguageModel
    except ImportError:
        logger.error("eval_missing_deps", hint="pip install unsloth")
        sys.exit(1)

    # Load adapter
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=adapter_path,
        max_seq_length=MAX_SEQ_LENGTH,
        load_in_4bit=True,
    )
    FastLanguageModel.for_inference(model)

    results = []
    for i, case in enumerate(cases):
        prompt = case["input"]
        expected_verdict = case.get("expected_verdict")

        inputs = tokenizer(prompt, return_tensors="pt").to("cuda")
        outputs = model.generate(
            **inputs,
            max_new_tokens=1024,
            temperature=0.1,
            do_sample=False,
        )
        response = tokenizer.decode(outputs[0], skip_special_tokens=True)
        response = response[len(prompt):]  # strip prompt echo

        scores = _score_response(response)

        # Check verdict matches expected (if provided)
        verdict_correct = None
        if expected_verdict:
            verdict_correct = expected_verdict.upper() in response.upper()

        results.append({
            "case_id": i,
            "ticker": case.get("ticker", "unknown"),
            "verdict_correct": verdict_correct,
            **scores,
        })

        logger.info(
            "eval_case_done",
            case_id=i,
            ticker=case.get("ticker"),
            has_verdict=scores["has_verdict"],
            has_thinking=scores["has_thinking"],
            format_score=scores["format_score"],
        )

    # ── Aggregate metrics ──────────────────────────────────────────────────────
    n = len(results)
    verdict_rate = sum(r["has_verdict"] for r in results) / n
    thinking_rate = sum(r["has_thinking"] for r in results) / n
    avg_format = sum(r["format_score"] for r in results) / n
    correct_verdicts = [r for r in results if r["verdict_correct"] is not None]
    verdict_accuracy = (
        sum(r["verdict_correct"] for r in correct_verdicts) / len(correct_verdicts)
        if correct_verdicts else None
    )

    passed = (
        verdict_rate >= EVAL_MIN_VERDICT_RATE
        and thinking_rate >= EVAL_MIN_THINKING_RATE
    )

    report = {
        "version": version,
        "adapter_path": adapter_path,
        "test_cases": n,
        "metrics": {
            "verdict_rate": round(verdict_rate, 3),
            "thinking_rate": round(thinking_rate, 3),
            "avg_format_score": round(avg_format, 3),
            "verdict_accuracy": round(verdict_accuracy, 3) if verdict_accuracy else None,
        },
        "thresholds": {
            "min_verdict_rate": EVAL_MIN_VERDICT_RATE,
            "min_thinking_rate": EVAL_MIN_THINKING_RATE,
        },
        "passed": passed,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }

    # Save report
    out_dir = Path(REPORTS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"eval_{version}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.json"
    report_path.write_text(json.dumps(report, indent=2))

    logger.info(
        "eval_complete",
        passed=passed,
        verdict_rate=round(verdict_rate, 3),
        thinking_rate=round(thinking_rate, 3),
        avg_format=round(avg_format, 3),
        report=str(report_path),
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", required=True, help="Path to new adapter directory")
    parser.add_argument("--version", required=True)
    parser.add_argument("--test-cases", default=EVAL_TEST_CASES_PATH)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    report = evaluate(args.adapter, args.version, args.test_cases, args.dry_run)
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, indent=2))
    sys.exit(0 if report["passed"] else 1)
