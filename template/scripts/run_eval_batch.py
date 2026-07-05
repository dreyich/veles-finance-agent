#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Eval Batch Runner - Golden Dataset Factory
==========================================
Submits financial questions to the async chat endpoint, polls for results,
extracts WORM traces, and saves successful runs to the golden dataset.

Usage:
    python scripts/run_eval_batch.py
    python scripts/run_eval_batch.py --questions my_qs.json
    python scripts/run_eval_batch.py --category fx_forecast
    python scripts/run_eval_batch.py --base-url http://prod:8000 --max-concurrency 5
"""
import sys
import os

# Force UTF-8 output on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import argparse
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

# -- Config -------------------------------------------------------------------

DEFAULT_BASE_URL = "http://localhost:8000/api/v1"
DEFAULT_EMAIL = "eval@veles.ai"
DEFAULT_PASSWORD = "EvalRunner2026!"
DEFAULT_USERNAME = "Eval Runner"
POLL_INTERVAL_S = 3
POLL_TIMEOUT_S = 300
MAX_CONCURRENCY = 3

GOLDEN_DATASET_DIR = Path(__file__).parent.parent / "app" / "data" / "golden_dataset"
WORM_LOG_PATH = Path("/app/logs/audit/worm.jsonl")

# -- Eval Question Set --------------------------------------------------------
# Diverse coverage: FX, macro, equity, debt, sandbox math

BUILT_IN_QUESTIONS = [
    # FX / Macro
    {
        "id": "fx_01",
        "category": "fx_current",
        "question": "Який зараз офіційний курс долара НБУ?",
        "expected_intent": "fx_rate",
        "expected_tools": ["get_fx_rates"],
        "notes": "Simple current-rate query. Should call get_fx_rates, return rate 40-60.",
    },
    {
        "id": "fx_02",
        "category": "fx_forecast",
        "question": "Який буде курс долара до кінця 2026 року? Дай прогноз з трьома сценаріями.",
        "expected_intent": "forecast",
        "expected_tools": ["get_fx_rates", "calculate_irp"],
        "notes": "Multi-step IRP forecast. Must return rate_forecast, rate_bull, rate_bear.",
    },
    {
        "id": "fx_03",
        "category": "fx_cross",
        "question": "Скільки коштує євро зараз відносно гривні?",
        "expected_intent": "fx_rate",
        "expected_tools": ["get_fx_rates"],
        "notes": "Cross-rate EUR/UAH.",
    },
    # Macro
    {
        "id": "macro_01",
        "category": "macro_us",
        "question": "Яка зараз ставка Федеральної резервної системи США і як це впливає на долар?",
        "expected_intent": "macro",
        "expected_tools": ["get_us_macro_data"],
        "notes": "US macro analysis.",
    },
    {
        "id": "macro_02",
        "category": "macro_yield",
        "question": "Чи перевернута крива дохідності США? Що це означає для економіки?",
        "expected_intent": "macro",
        "expected_tools": ["get_yield_curve", "get_us_macro_data"],
        "notes": "Yield curve inversion signal.",
    },
    # Equity
    {
        "id": "eq_01",
        "category": "equity_price",
        "question": "Яка зараз ціна акцій NVIDIA (NVDA) і яке P/E?",
        "expected_intent": "equity",
        "expected_tools": ["get_market_data"],
        "notes": "Simple equity query.",
    },
    {
        "id": "eq_02",
        "category": "equity_dcf",
        "question": "Порахуй intrinsic value для Apple (AAPL) з FCF $100B, WACC 9%, terminal growth 2.5%",
        "expected_intent": "calculation",
        "expected_tools": ["calculate_dcf"],
        "notes": "DCF valuation with explicit params.",
    },
    # Sandbox math
    {
        "id": "sandbox_01",
        "category": "sandbox_kelly",
        "question": "Яким має бути розмір позиції якщо ймовірність виграшу 60% і ризик/нагорода 2:1? Критерій Келлі.",
        "expected_intent": "calculation",
        "expected_tools": ["kelly_criterion_calculator"],
        "notes": "Kelly criterion.",
    },
    {
        "id": "sandbox_02",
        "category": "sandbox_montecarlo",
        "question": "Запусти Monte Carlo (10000 ітерацій) для курсу USD/UAH через 6 місяців з рівня 44.92 і волатильністю 0.5% в день",
        "expected_intent": "calculation",
        "expected_tools": ["execute_python_sandbox"],
        "notes": "Sandbox Monte Carlo simulation.",
    },
    # Chat
    {
        "id": "chat_01",
        "category": "chat",
        "question": "Привіт! Що ти вмієш робити?",
        "expected_intent": "chat",
        "expected_tools": [],
        "notes": "Simple greeting. No tools needed.",
    },
]


# -- Auth helpers -------------------------------------------------------------

async def get_user_token(client: httpx.AsyncClient, base_url: str, email: str, password: str) -> str:
    await client.post(f"{base_url}/auth/register", json={
        "email": email, "password": password, "username": DEFAULT_USERNAME
    })
    r = await client.post(f"{base_url}/auth/login", data={
        "email": email, "password": password, "grant_type": "password"
    })
    r.raise_for_status()
    return r.json()["access_token"]


async def get_session_token(client: httpx.AsyncClient, base_url: str, user_token: str) -> tuple:
    r = await client.post(
        f"{base_url}/auth/session",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    r.raise_for_status()
    data = r.json()
    return data["token"]["access_token"], data["session_id"]


# -- Job helpers --------------------------------------------------------------

async def submit_job(client: httpx.AsyncClient, base_url: str, session_token: str, question: str) -> tuple:
    r = await client.post(
        f"{base_url}/chatbot/chat/async",
        headers={"Authorization": f"Bearer {session_token}", "Content-Type": "application/json"},
        json={"messages": [{"role": "user", "content": question}]},
    )
    r.raise_for_status()
    data = r.json()
    return data["job_id"], data["poll_url"]


async def poll_job(client: httpx.AsyncClient, base_url: str, session_token: str, job_id: str, timeout_s: int = POLL_TIMEOUT_S) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        r = await client.get(
            f"{base_url}/chatbot/jobs/{job_id}",
            headers={"Authorization": f"Bearer {session_token}"},
        )
        if r.status_code == 404:
            raise RuntimeError(f"Job {job_id} not found")
        r.raise_for_status()
        data = r.json()
        if data.get("status") in ("done", "error"):
            return data
        await asyncio.sleep(POLL_INTERVAL_S)
    raise TimeoutError(f"Job {job_id} did not complete within {timeout_s}s")


# -- WORM log helpers ---------------------------------------------------------

def load_worm_entries(session_id: str) -> list:
    if not WORM_LOG_PATH.exists():
        return []
    entries = []
    for line in WORM_LOG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            if entry.get("session_id") == session_id:
                entries.append(entry)
        except json.JSONDecodeError:
            pass
    return entries


def extract_token_stats(worm_entries: list) -> dict:
    # Prefer the llm_end entry with non-zero completion tokens (the _chat node
    # writes a direct entry with char-based fallback; the callback entry may be 0).
    best: Optional[dict] = None
    for entry in worm_entries:
        if entry.get("step_type") != "llm_end":
            continue
        tokens = entry.get("payload", {}).get("tokens", {})
        if best is None or tokens.get("completion", 0) > best.get("payload", {}).get("tokens", {}).get("completion", 0):
            best = entry
    if best is None:
        return {}
    tokens = best.get("payload", {}).get("tokens", {})
    duration = best.get("payload", {}).get("duration_ms", 0)
    return {
        "prompt_tokens": tokens.get("prompt", 0),
        "completion_tokens": tokens.get("completion", 0),
        "total_tokens": tokens.get("total", 0),
        "tps": tokens.get("tps", 0),
        "llm_duration_ms": duration,
    }


# -- Auto-grader --------------------------------------------------------------

def auto_grade(result: dict, question_meta: dict, envelope: Optional[dict]) -> dict:
    reasons = []
    score = 0

    if result.get("status") == "done":
        score += 25
        reasons.append("[OK] job completed successfully")
    else:
        reasons.append(f"[FAIL] job status={result.get('status')} error={str(result.get('error',''))[:80]}")
        return {"passed": False, "score": 0, "reasons": reasons}

    if envelope:
        score += 25
        reasons.append(f"[OK] UniversalEnvelope parsed (intent={envelope.get('intent')})")
    else:
        reasons.append("[FAIL] envelope not parsed from response")

    if envelope and envelope.get("intent") == question_meta.get("expected_intent"):
        score += 25
        reasons.append(f"[OK] intent matches ({question_meta['expected_intent']})")
    elif envelope:
        reasons.append(f"[~] intent mismatch: got={envelope.get('intent')} expected={question_meta.get('expected_intent')}")

    if envelope and question_meta.get("expected_intent") in ("fx_rate", "forecast", "equity", "calculation"):
        if envelope.get("financial_data"):
            score += 25
            reasons.append("[OK] financial_data populated")
        else:
            reasons.append("[~] financial_data is null")

    if question_meta.get("expected_intent") == "forecast" and envelope:
        fd = envelope.get("financial_data") or {}
        if fd.get("rate_forecast") and fd.get("rate_bull") and fd.get("rate_bear"):
            reasons.append(f"[OK] 3 scenarios: base={fd['rate_forecast']} bull={fd['rate_bull']} bear={fd['rate_bear']}")
        else:
            reasons.append("[~] missing bull/bear scenarios")

    return {"passed": score >= 50, "score": score, "reasons": reasons}


# -- Main eval runner ---------------------------------------------------------

async def run_eval(questions: list, base_url: str, email: str, password: str, max_concurrency: int, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"VELES EVAL BATCH RUNNER")
    print(f"{'='*60}")
    print(f"Questions:   {len(questions)}")
    print(f"Endpoint:    {base_url}")
    print(f"Output:      {output_dir}")
    print(f"Concurrency: {max_concurrency}")
    print(f"{'='*60}\n")

    async with httpx.AsyncClient(timeout=30) as auth_client:
        user_token = await get_user_token(auth_client, base_url, email, password)
        print(f"[AUTH] Logged in as {email}\n")

    semaphore = asyncio.Semaphore(max_concurrency)

    async def process_question(q: dict) -> dict:
        async with semaphore:
            qid = q["id"]
            print(f"[{qid}] Submitting: '{q['question'][:55]}...'")
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    session_token, session_id = await get_session_token(client, base_url, user_token)
                    t_submit = time.monotonic()
                    job_id, poll_url = await submit_job(client, base_url, session_token, q["question"])
                    print(f"[{qid}] Polling job_id={job_id[:8]}...")

                    job_result = await poll_job(client, base_url, session_token, job_id)
                    total_ms = (time.monotonic() - t_submit) * 1000

                envelope = job_result.get("envelope")
                await asyncio.sleep(2)  # let WORM background write complete

                worm_entries = load_worm_entries(session_id)
                token_stats = extract_token_stats(worm_entries)
                grade = auto_grade(job_result, q, envelope)

                status_str = "PASS" if grade["passed"] else "FAIL"
                print(f"[{qid}] [{status_str}] score={grade['score']}/100 | "
                      f"{total_ms/1000:.1f}s | "
                      f"tokens={token_stats.get('total_tokens', 0)} | "
                      f"intent={envelope.get('intent') if envelope else 'N/A'}")
                for reason in grade["reasons"]:
                    print(f"       {reason}")
                print()

                record = {
                    "id": qid,
                    "category": q["category"],
                    "question": q["question"],
                    "expected_intent": q["expected_intent"],
                    "expected_tools": q.get("expected_tools", []),
                    "notes": q.get("notes", ""),
                    "job_id": job_id,
                    "session_id": session_id,
                    "status": job_result.get("status"),
                    "envelope": envelope,
                    "messages": job_result.get("messages", []),
                    "worm_trace": worm_entries,
                    "token_stats": token_stats,
                    "total_duration_ms": round(total_ms, 1),
                    "grade": grade,
                    "quality_score": None,
                    "used_for_training": False,
                    "evaluated_at": datetime.now(timezone.utc).isoformat(),
                }

                suffix = "success" if grade["passed"] else "failed"
                fname = output_dir / f"{qid}_{suffix}.json"
                fname.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
                return record

            except Exception as exc:
                import traceback
                print(f"[{qid}] [ERROR] {type(exc).__name__}: {exc}")
                traceback.print_exc()
                record = {
                    "id": qid,
                    "question": q["question"],
                    "status": "exception",
                    "error": str(exc),
                    "grade": {"passed": False, "score": 0, "reasons": [f"Exception: {exc}"]},
                }
                (output_dir / f"{qid}_exception.json").write_text(
                    json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                return record

    tasks = [process_question(q) for q in questions]
    all_results = await asyncio.gather(*tasks)

    passed = sum(1 for r in all_results if r.get("grade", {}).get("passed"))
    avg_score = sum(r.get("grade", {}).get("score", 0) for r in all_results) / len(all_results)
    avg_ms = sum(r.get("total_duration_ms", 0) for r in all_results if r.get("total_duration_ms")) / max(1, len(all_results))

    intent_breakdown = {}
    for r in all_results:
        intent = (r.get("envelope") or {}).get("intent", "N/A")
        intent_breakdown[intent] = intent_breakdown.get(intent, 0) + 1

    summary = {
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "total_questions": len(questions),
        "passed": passed,
        "failed": len(all_results) - passed,
        "pass_rate_pct": round(passed / len(questions) * 100, 1),
        "avg_score": round(avg_score, 1),
        "avg_duration_ms": round(avg_ms, 1),
        "intent_breakdown": intent_breakdown,
        "golden_dataset_dir": str(output_dir),
    }

    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 60)
    print("EVAL COMPLETE")
    print("=" * 60)
    print(f"  Passed:      {passed}/{len(questions)} ({summary['pass_rate_pct']}%)")
    print(f"  Avg score:   {avg_score:.1f}/100")
    print(f"  Avg latency: {avg_ms/1000:.1f}s")
    print(f"  Intents:     {intent_breakdown}")
    print(f"  Output:      {output_dir}")
    print("=" * 60)


# -- CLI ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Veles Eval Batch Runner")
    parser.add_argument("--questions", type=Path)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--max-concurrency", type=int, default=MAX_CONCURRENCY)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--category", help="Filter by category prefix")
    args = parser.parse_args()

    if args.questions and args.questions.exists():
        questions = json.loads(args.questions.read_text(encoding="utf-8"))
        print(f"Loaded {len(questions)} questions from {args.questions}")
    else:
        questions = BUILT_IN_QUESTIONS

    if args.category:
        questions = [q for q in questions if q.get("category", "").startswith(args.category)]
        print(f"Filtered to {len(questions)} questions in category '{args.category}'")

    if not questions:
        print("No questions to run.")
        sys.exit(1)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or (GOLDEN_DATASET_DIR / f"run_{ts}")

    asyncio.run(run_eval(
        questions=questions,
        base_url=args.base_url,
        email=args.email,
        password=args.password,
        max_concurrency=args.max_concurrency,
        output_dir=output_dir,
    ))


if __name__ == "__main__":
    main()
