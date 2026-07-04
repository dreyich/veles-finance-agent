"""
Lightweight orchestrator regression eval — no GPU/model download needed.

Tests agent/graph.py's tool-routing decisions directly against the real Groq
API (temperature=0, so deterministic enough for CI). This targets exactly the
kind of regression found during the 2026-07-04 debugging session: wrong
ticker resolution from non-English/declined company names, and the
orchestrator calling irrelevant tools (each of which makes a live network
call) for narrowly-scoped requests.

Does NOT execute tools (no yfinance/SEC EDGAR calls) — only checks which
tool(s) the orchestrator's first turn decides to call and with what args.
Requires GROQ_API_KEY in the environment.
"""
import os
import sys

from langchain_core.messages import HumanMessage

from agent.graph import orchestrator_with_tools, SYSTEM_PROMPT

CASES = [
    {
        "name": "ticker resolution — Ukrainian genitive case",
        "message": "витащи найцікавіші цифри з останнього 10-к тесли",
        "must_call": ["fetch_sec_10k_tool"],
        "must_not_call": ["screen_stocks", "get_market_data", "due_diligence_report"],
        "expect_ticker": "TSLA",
    },
    {
        "name": "narrow trend question doesn't trigger unrelated tools",
        "message": "Compare Microsoft revenue and margin over the last two years",
        "must_call": ["compare_annual_reports"],
        "must_not_call": ["screen_stocks", "get_market_data", "due_diligence_report", "kelly_position_size"],
        "expect_ticker": "MSFT",
    },
    {
        "name": "screening request uses screen_stocks, not a single-ticker tool",
        "message": "Find tech stocks with P/E below 30 and margin above 15%",
        "must_call": ["screen_stocks"],
        "must_not_call": ["fetch_sec_10k_tool", "compare_annual_reports", "due_diligence_report"],
        "expect_ticker": None,
    },
]


def run_case(case: dict) -> tuple[bool, str]:
    response = orchestrator_with_tools.invoke(
        [SYSTEM_PROMPT, HumanMessage(content=case["message"])]
    )
    calls = getattr(response, "tool_calls", None) or []
    called_names = [c["name"] for c in calls]

    problems = []
    for required in case["must_call"]:
        if required not in called_names:
            problems.append(f"missing required tool call: {required}")
    for forbidden in case["must_not_call"]:
        if forbidden in called_names:
            problems.append(f"called forbidden tool: {forbidden}")

    if case["expect_ticker"]:
        tickers = [c["args"].get("ticker") for c in calls if "ticker" in c.get("args", {})]
        if case["expect_ticker"] not in tickers:
            problems.append(f"expected ticker {case['expect_ticker']}, got {tickers}")

    ok = not problems
    detail = f"tools_called={called_names}" + (f"  problems={problems}" if problems else "")
    return ok, detail


def main() -> int:
    if not os.getenv("GROQ_API_KEY") and not os.getenv("ORCHESTRATOR_API_KEY"):
        print("SKIP: GROQ_API_KEY/ORCHESTRATOR_API_KEY not set")
        return 0

    failures = 0
    for case in CASES:
        ok, detail = run_case(case)
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {case['name']}\n       {detail}")
        if not ok:
            failures += 1

    print(f"\n{failures}/{len(CASES)} cases failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
