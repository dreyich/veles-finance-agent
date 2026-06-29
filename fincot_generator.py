"""
FinCoT Generator — Veles Finance Dataset Builder
Reads sec_10k.db, generates chain-of-thought financial analyses,
saves to fin_dataset.jsonl in ShareGPT format for Unsloth QLoRA.

Usage:
    python fincot_generator.py                  # generate all
    python fincot_generator.py --limit 50       # first 50 samples
    python fincot_generator.py --ticker AAPL    # single company
    python fincot_generator.py --dry-run        # show prompts only
    python fincot_generator.py --status         # dataset stats
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import httpx

DB_PATH   = Path(__file__).parent / "data" / "sec_10k.db"
OUT_PATH  = Path(__file__).parent / "data" / "fin_dataset.jsonl"
API_URL   = "http://localhost:11434/v1"       # local Ollama / SGLang
MODEL     = "veles-finance:latest"            # or "drushka/veles-finance-7b-v5"

# ── Expert Blueprint injected into every system prompt ────────────────────
EXPERT_BLUEPRINT = """
Financial Analysis Blueprint:
1. IDENTIFY  → locate the relevant metric(s) in the provided data
2. CALCULATE → perform exact arithmetic, show intermediate steps
3. BENCHMARK → compare to industry norms or prior period
4. REASON    → explain the business driver behind the number
5. CONCLUDE  → give a concise, actionable verdict
Always cite the specific numbers from the context before reasoning.
""".strip()

SYSTEM_PROMPT = f"""You are a senior CFA-certified financial analyst with 20 years of experience \
analyzing Fortune 500 SEC filings.

{EXPERT_BLUEPRINT}

When answering:
- Use <thinking> tags for step-by-step calculations and reasoning
- Use <output> tags for the final clean answer with a brief self-check
- Be precise: quote figures from the data, show arithmetic, state units
- Flag data limitations honestly"""

# ── Question templates per analysis type ──────────────────────────────────
QUESTION_TEMPLATES = [
    # Growth analysis
    "Calculate the YoY revenue growth for {company} ({ticker}) from the provided financials. "
    "Identify the primary business driver behind this trend.",

    # Profitability
    "Analyze {company}'s ({ticker}) net profit margin. Is it improving or deteriorating? "
    "What does this imply about operational efficiency?",

    # Leverage
    "Assess the financial leverage of {company} ({ticker}) using the available debt and equity figures. "
    "What is the debt-to-equity ratio and what risk does it pose?",

    # Cash generation
    "Evaluate {company}'s ({ticker}) cash generation quality. "
    "How does operating cash flow compare to net income, and what does the difference reveal?",

    # Peer comparison (requires two companies)
    "Compare {company}'s ({ticker}) revenue and net income margin against {peer} ({peer_ticker}). "
    "Which company demonstrates superior financial performance and why?",

    # EPS analysis
    "Analyze the earnings per share (EPS) for {company} ({ticker}). "
    "What does this figure imply for shareholder value creation?",

    # Asset efficiency
    "Calculate the return on assets (ROA) for {company} ({ticker}) using net income and total assets. "
    "How efficiently is management deploying the asset base?",

    # Investment screening
    "Based solely on the financial data provided, would you classify {company} ({ticker}) "
    "as a STRONG BUY, BUY, HOLD, or AVOID? Justify with specific metrics.",

    # Risk assessment
    "Identify the top three financial risks for {company} ({ticker}) based on its balance sheet "
    "and income statement. Quantify each risk where possible.",

    # Kelly Criterion
    "Given {company}'s ({ticker}) historical earnings stability and the provided financial metrics, "
    "estimate an appropriate position size using the Kelly Criterion framework. "
    "Assume a moderate-risk investor with a 60% historical win rate and 1.4x win/loss ratio.",
]

def fmt_billions(val: float | None) -> str:
    if val is None: return "N/A"
    if abs(val) >= 1e9: return f"${val/1e9:.2f}B"
    if abs(val) >= 1e6: return f"${val/1e6:.2f}M"
    return f"${val:,.0f}"


def build_context(row: dict, peer: dict | None = None) -> str:
    """Format SEC data into a structured financial context block."""
    lines = [
        f"Company: {row['company']} ({row['ticker']})",
        f"Fiscal Year: {row['fiscal_year']} | Period End: {row['period_end']}",
        "",
        "=== INCOME STATEMENT ===",
        f"Revenue:         {fmt_billions(row['revenue'])}",
        f"Net Income:      {fmt_billions(row['net_income'])}",
        f"EPS (diluted):   ${row['eps']:.2f}" if row['eps'] else "EPS (diluted):   N/A",
    ]
    if row['revenue'] and row['net_income']:
        margin = row['net_income'] / row['revenue'] * 100
        lines.append(f"Net Margin:      {margin:.1f}%")

    lines += [
        "",
        "=== BALANCE SHEET ===",
        f"Total Assets:    {fmt_billions(row['total_assets'])}",
        f"Total Debt:      {fmt_billions(row['total_debt'])}",
        f"Shareholders' Equity: {fmt_billions(row['equity'])}",
    ]
    if row['total_assets'] and row['equity']:
        de = (row['total_debt'] or 0) / row['equity'] if row['equity'] else None
        if de: lines.append(f"Debt/Equity:     {de:.2f}x")

    lines += [
        "",
        "=== CASH FLOW ===",
        f"Operating Cash Flow: {fmt_billions(row['op_cash_flow'])}",
    ]
    if row['op_cash_flow'] and row['net_income']:
        ocf_ratio = row['op_cash_flow'] / row['net_income'] if row['net_income'] else None
        if ocf_ratio: lines.append(f"OCF / Net Income: {ocf_ratio:.2f}x")

    if peer:
        lines += [
            "",
            f"=== PEER COMPARISON: {peer['company']} ({peer['ticker']}) FY{peer['fiscal_year']} ===",
            f"Revenue:         {fmt_billions(peer['revenue'])}",
            f"Net Income:      {fmt_billions(peer['net_income'])}",
        ]
        if peer['revenue'] and peer['net_income']:
            pm = peer['net_income'] / peer['revenue'] * 100
            lines.append(f"Net Margin:      {pm:.1f}%")

    return "\n".join(lines)


def build_sample(row: dict, template: str, peer: dict | None = None) -> dict:
    """Build one ShareGPT conversation dict."""
    kwargs = {
        "company": row["company"],
        "ticker":  row["ticker"],
        "peer":        peer["company"]  if peer else "",
        "peer_ticker": peer["ticker"]   if peer else "",
    }
    question = template.format(**kwargs)
    context  = build_context(row, peer)
    user_msg = f"Context:\n{context}\n\nQuestion: {question}"

    return {
        "conversations": [
            {"from": "system",    "value": SYSTEM_PROMPT},
            {"from": "user",      "value": user_msg},
            {"from": "assistant", "value": "__PLACEHOLDER__"},
        ],
        "_meta": {
            "ticker":      row["ticker"],
            "fiscal_year": row["fiscal_year"],
            "template":    template[:60],
            "generated":   datetime.now(datetime.UTC).isoformat() if hasattr(datetime, 'UTC') else datetime.utcnow().isoformat(),
        }
    }


def call_model(prompt_messages: list[dict], timeout: float = 90.0) -> str:
    """Call local Ollama / SGLang via OpenAI-compatible API."""
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(f"{API_URL}/chat/completions", json={
                "model": MODEL,
                "messages": prompt_messages,
                "temperature": 0.3,
                "max_tokens": 1024,
            })
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"<error>{e}</error>"


def load_rows(conn: sqlite3.Connection, ticker: str | None = None) -> list[dict]:
    q = "SELECT * FROM filings WHERE revenue IS NOT NULL"
    params = []
    if ticker:
        q += " AND ticker = ?"
        params.append(ticker.upper())
    q += " ORDER BY ticker, fiscal_year DESC"
    conn.row_factory = sqlite3.Row
    rows = conn.execute(q, params).fetchall()
    return [dict(r) for r in rows]


def print_status():
    if not OUT_PATH.exists():
        print("No dataset yet. Run without --status to generate.")
        return
    with open(OUT_PATH) as f:
        lines = [json.loads(l) for l in f if l.strip()]
    tickers = {l["_meta"]["ticker"] for l in lines}
    complete = sum(1 for l in lines if "__PLACEHOLDER__" not in l["conversations"][2]["value"])
    print(f"\n{'='*50}")
    print(f"Dataset: {OUT_PATH}")
    print(f"Total samples:    {len(lines)}")
    print(f"With AI response: {complete}")
    print(f"Unique tickers:   {len(tickers)}")
    print(f"{'='*50}\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker",  help="Single ticker to process")
    parser.add_argument("--limit",   type=int, help="Max samples to generate")
    parser.add_argument("--dry-run", action="store_true", help="Print prompts, no API calls")
    parser.add_argument("--status",  action="store_true")
    parser.add_argument("--delay",   type=float, default=0.5)
    args = parser.parse_args()

    if args.status:
        print_status(); return

    conn  = sqlite3.connect(DB_PATH)
    rows  = load_rows(conn, args.ticker)
    print(f"Loaded {len(rows)} filings from DB")

    # Build samples: one question per template per company, plus peer comparisons
    samples = []
    for row in rows:
        for template in QUESTION_TEMPLATES:
            if "{peer}" in template:
                others = [r for r in rows if r["ticker"] != row["ticker"]]
                if not others: continue
                peer = random.choice(others)
            else:
                peer = None
            samples.append(build_sample(row, template, peer))

    random.shuffle(samples)
    if args.limit:
        samples = samples[:args.limit]

    print(f"Samples to generate: {len(samples)}")
    OUT_PATH.parent.mkdir(exist_ok=True)

    done = ok = errors = 0
    with open(OUT_PATH, "a") as f:
        for i, sample in enumerate(samples, 1):
            convs   = sample["conversations"]
            msgs    = convs[:2]   # system + user

            if args.dry_run:
                print(f"\n--- Sample {i} [{sample['_meta']['ticker']}] ---")
                print(msgs[1]["value"][:400])
                print("...")
                continue

            print(f"[{i}/{len(samples)}] {sample['_meta']['ticker']} — generating...", end=" ", flush=True)
            response = call_model(msgs)

            # Validate response has thinking + output tags
            if "<thinking>" in response and "<output>" in response:
                convs[2]["value"] = response
                ok += 1
                print("✓")
            else:
                # Still save but mark for review
                convs[2]["value"] = response
                print("⚠ (no tags)")

            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
            f.flush()
            done += 1
            time.sleep(args.delay)

    if not args.dry_run:
        print(f"\nDone: {done} saved, {ok} with proper FinCoT tags")
        print_status()


if __name__ == "__main__":
    main()
