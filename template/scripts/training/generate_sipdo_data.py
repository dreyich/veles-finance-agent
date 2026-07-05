"""
SIPDO Synthetic Financial Data Generator
=========================================
SIPDO = Synthetic Instruction Pair Data Optimization

Architecture:
  ┌─────────────────┐    ┌──────────────┐    ┌─────────────┐
  │  Fin-Generator  │ -> │ Fin-Verifier │ -> │  JSONL File │
  │  (LLM + yfinance│    │  (Math/Fact) │    │  (Training) │
  └─────────────────┘    └──────────────┘    └─────────────┘

Two classes of Q&A pairs generated:

  CLASS 1 — Deterministic Math (verifiable by formula):
    Kelly Criterion, Sharpe Ratio, Max Drawdown, Position Sizing

  CLASS 2 — Real Market Data (verifiable by fact-check vs yfinance):
    P/E analysis, market cap calculation, revenue growth,
    52-week range, analyst consensus, news sentiment

Usage:
  # With OpenRouter (free tier):
  export OPENAI_API_KEY="sk-or-..."
  export OPENAI_BASE_URL="https://openrouter.ai/api/v1"
  python generate_sipdo_data.py --n 200 --output finance_qa.jsonl

  # Default model (Qwen 72B, free on OpenRouter):
  python generate_sipdo_data.py --model qwen/qwen-2.5-72b-instruct --n 200
"""

import argparse
import json
import math
import os
import random
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from rich.console import Console
    from rich.progress import track

    console = Console()
    log = console.print
except ImportError:
    log = print

    def track(iterable, description=""):
        return iterable


try:
    from openai import OpenAI
except ImportError:
    raise ImportError("pip install openai")

try:
    import yfinance as yf

    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    log("[yellow]yfinance not installed — CLASS 2 scenarios disabled[/yellow]")


# ── CLASS 1: Deterministic Math Verifiers ────────────────────────────────────

def kelly_criterion(p: float, b: float) -> float:
    return (p * b - (1 - p)) / b


def sharpe_ratio(returns: list[float], risk_free: float = 0.0) -> float:
    n = len(returns)
    mean = sum(returns) / n
    variance = sum((r - mean) ** 2 for r in returns) / n
    std = math.sqrt(variance)
    return (mean - risk_free) / std if std > 0 else 0.0


def max_drawdown(prices: list[float]) -> float:
    peak, max_dd = prices[0], 0.0
    for p in prices:
        if p > peak:
            peak = p
        dd = (peak - p) / peak
        if dd > max_dd:
            max_dd = dd
    return max_dd


def position_size_risk(account: float, risk_pct: float, entry: float, stop: float) -> float:
    risk_amount = account * (risk_pct / 100)
    per_share_risk = abs(entry - stop)
    return risk_amount / per_share_risk if per_share_risk > 0 else 0


def verify_numeric(answer: str, expected: float, tolerance: float = 0.02) -> bool:
    numbers = re.findall(r"-?\d+\.?\d*", answer.replace(",", ""))
    for s in numbers:
        try:
            if abs(float(s) - expected) / (abs(expected) + 1e-9) < tolerance:
                return True
        except ValueError:
            continue
    return False


def _gen_kelly_scenario() -> dict:
    p = round(random.uniform(0.45, 0.75), 2)
    b = round(random.uniform(1.0, 4.0), 2)
    f = kelly_criterion(p, b)
    return {
        "type": "kelly_criterion",
        "params": {"p": p, "b": b},
        "expected": round(f, 4),
        "question": (
            f"A trader has a strategy with a {p*100:.0f}% win rate and an average "
            f"win/loss ratio of {b:.1f}. Using the Kelly Criterion formula "
            f"f* = (p*b - q) / b, what is the optimal fraction of capital "
            f"to risk per trade? Give the answer as a percentage."
        ),
        "answer_check": lambda ans: verify_numeric(ans, f * 100),
    }


def _gen_sharpe_scenario() -> dict:
    returns = [round(random.gauss(0.01, 0.03), 4) for _ in range(12)]
    sr = sharpe_ratio(returns)
    ret_str = ", ".join(f"{r:.4f}" for r in returns)
    return {
        "type": "sharpe_ratio",
        "params": {"returns": returns},
        "expected": round(sr, 4),
        "question": (
            f"Calculate the Sharpe Ratio (assume 0% risk-free rate) for a portfolio "
            f"with these monthly returns: [{ret_str}]. Show your calculation."
        ),
        "answer_check": lambda ans: verify_numeric(ans, sr, tolerance=0.05),
    }


def _gen_position_size_scenario() -> dict:
    account = random.choice([10_000, 25_000, 50_000, 100_000])
    risk_pct = random.choice([1.0, 1.5, 2.0])
    entry = round(random.uniform(50, 500), 2)
    stop = round(entry * random.uniform(0.92, 0.98), 2)
    size = position_size_risk(account, risk_pct, entry, stop)
    return {
        "type": "position_sizing",
        "params": {"account": account, "risk_pct": risk_pct, "entry": entry, "stop": stop},
        "expected": round(size, 2),
        "question": (
            f"A trader has a ${account:,} account and risks {risk_pct}% per trade. "
            f"They want to buy a stock at ${entry:.2f} with a stop-loss at ${stop:.2f}. "
            f"How many shares should they buy? Round to the nearest whole share."
        ),
        "answer_check": lambda ans: verify_numeric(ans, size, tolerance=0.05),
    }


def _gen_max_drawdown_scenario() -> dict:
    start = random.uniform(100, 1000)
    prices = [start]
    for _ in range(11):
        prices.append(round(prices[-1] * random.uniform(0.90, 1.12), 2))
    dd = max_drawdown(prices)
    prices_str = ", ".join(f"${p:.2f}" for p in prices)
    return {
        "type": "max_drawdown",
        "params": {"prices": prices},
        "expected": round(dd * 100, 2),
        "question": (
            f"Calculate the Maximum Drawdown percentage for this portfolio equity curve: "
            f"[{prices_str}]. Formula: MDD = (Peak - Trough) / Peak × 100."
        ),
        "answer_check": lambda ans: verify_numeric(ans, dd * 100, tolerance=0.05),
    }


# ── CLASS 2: Real Market Data Scenarios (yfinance) ───────────────────────────

_TICKERS = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "BRK-B",
    "JPM", "V", "MA", "UNH", "XOM", "JNJ", "WMT", "PG", "HD", "BAC",
    "AVGO", "LLY", "MRK", "ABBV", "PEP", "KO", "ORCL", "CSCO", "ADBE",
    "AMD", "INTC", "QCOM", "TXN", "CRM", "NOW", "PANW", "SNOW", "PLTR",
]


def _fetch_ticker_info(ticker: str) -> Optional[dict]:
    """Fetch real market data via yfinance. Returns None on failure."""
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        if not info.get("regularMarketPrice") and not info.get("currentPrice"):
            return None
        return info
    except Exception:
        return None


def _gen_pe_analysis_scenario() -> Optional[dict]:
    """Q&A about P/E valuation using real data."""
    ticker = random.choice(_TICKERS)
    info = _fetch_ticker_info(ticker)
    if not info:
        return None

    pe = info.get("trailingPE")
    fwd_pe = info.get("forwardPE")
    name = info.get("shortName", ticker)
    sector = info.get("sector", "Technology")

    if not pe or pe <= 0 or pe > 500:
        return None

    # Sector average P/E approximations (static, good enough for training data)
    sector_avg_pe = {
        "Technology": 28, "Healthcare": 22, "Financial Services": 14,
        "Consumer Cyclical": 20, "Communication Services": 18,
        "Energy": 12, "Utilities": 16, "Consumer Defensive": 20,
        "Industrials": 20, "Basic Materials": 15, "Real Estate": 30,
    }
    avg = sector_avg_pe.get(sector, 20)
    is_expensive = pe > avg * 1.2
    verdict = "overvalued" if is_expensive else ("fairly valued" if pe > avg * 0.8 else "undervalued")

    question = (
        f"{name} ({ticker}) has a trailing P/E ratio of {pe:.1f} and a forward P/E of "
        f"{fwd_pe:.1f if fwd_pe else 'N/A'}. "
        f"The {sector} sector average P/E is approximately {avg}x. "
        f"Is {ticker} overvalued, fairly valued, or undervalued relative to its sector? "
        f"Justify your answer."
    )

    def check(ans: str) -> bool:
        return verdict.lower() in ans.lower()

    return {
        "type": "pe_valuation",
        "params": {"ticker": ticker, "pe": pe, "fwd_pe": fwd_pe, "sector": sector, "sector_avg": avg},
        "expected": verdict,
        "question": question,
        "answer_check": check,
        "real_data": True,
    }


def _gen_market_cap_scenario() -> Optional[dict]:
    """Q&A about market cap calculation using real price + shares."""
    ticker = random.choice(_TICKERS)
    info = _fetch_ticker_info(ticker)
    if not info:
        return None

    price = info.get("currentPrice") or info.get("regularMarketPrice")
    shares = info.get("sharesOutstanding")
    mktcap = info.get("marketCap")
    name = info.get("shortName", ticker)

    if not price or not shares or not mktcap:
        return None

    calculated = price * shares
    # Allow 5% tolerance (intraday price drift)
    expected_b = mktcap / 1e9

    question = (
        f"{name} ({ticker}) has {shares/1e9:.2f} billion shares outstanding "
        f"and currently trades at ${price:.2f} per share. "
        f"Calculate the market capitalization in billions of dollars. "
        f"Round to two decimal places."
    )

    def check(ans: str) -> bool:
        return verify_numeric(ans, expected_b, tolerance=0.05)

    return {
        "type": "market_cap_calculation",
        "params": {"ticker": ticker, "price": price, "shares": shares},
        "expected": round(expected_b, 2),
        "question": question,
        "answer_check": check,
        "real_data": True,
    }


def _gen_52week_range_scenario() -> Optional[dict]:
    """Q&A about current price position within 52-week range."""
    ticker = random.choice(_TICKERS)
    info = _fetch_ticker_info(ticker)
    if not info:
        return None

    price = info.get("currentPrice") or info.get("regularMarketPrice")
    low = info.get("fiftyTwoWeekLow")
    high = info.get("fiftyTwoWeekHigh")
    name = info.get("shortName", ticker)

    if not all([price, low, high]) or high <= low:
        return None

    pct_from_low = ((price - low) / (high - low)) * 100
    pct_from_high = ((high - price) / high) * 100

    question = (
        f"{name} ({ticker}) currently trades at ${price:.2f}. "
        f"Its 52-week range is ${low:.2f} – ${high:.2f}. "
        f"What percentage of the 52-week range has the stock recovered from its low? "
        f"Also, how far (in %) is it from its 52-week high?"
    )

    def check(ans: str) -> bool:
        return verify_numeric(ans, pct_from_low, tolerance=0.05) or \
               verify_numeric(ans, pct_from_high, tolerance=0.05)

    return {
        "type": "52week_range",
        "params": {"ticker": ticker, "price": price, "low": low, "high": high},
        "expected": {"pct_from_low": round(pct_from_low, 2), "pct_from_high": round(pct_from_high, 2)},
        "question": question,
        "answer_check": check,
        "real_data": True,
    }


def _gen_analyst_consensus_scenario() -> Optional[dict]:
    """Q&A about analyst recommendations using real data."""
    ticker = random.choice(_TICKERS)
    info = _fetch_ticker_info(ticker)
    if not info:
        return None

    rec = info.get("recommendationKey", "")
    target = info.get("targetMeanPrice")
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    name = info.get("shortName", ticker)
    analysts = info.get("numberOfAnalystOpinions", 0)

    if not rec or not target or not price or analysts < 3:
        return None

    upside = ((target - price) / price) * 100

    question = (
        f"Based on analyst consensus data: {name} ({ticker}) has a mean price target "
        f"of ${target:.2f}, current price is ${price:.2f}, and analyst recommendation "
        f"is '{rec.upper().replace('_', ' ')}' ({analysts} analysts). "
        f"Calculate the implied upside/downside to the price target. "
        f"What does this suggest about the stock?"
    )

    def check(ans: str) -> bool:
        return verify_numeric(ans, upside, tolerance=0.05)

    return {
        "type": "analyst_consensus",
        "params": {"ticker": ticker, "target": target, "price": price, "rec": rec},
        "expected": round(upside, 2),
        "question": question,
        "answer_check": check,
        "real_data": True,
    }


def _gen_profit_margin_scenario() -> Optional[dict]:
    """Q&A about profitability using real gross/profit margins."""
    ticker = random.choice(_TICKERS)
    info = _fetch_ticker_info(ticker)
    if not info:
        return None

    gross_margin = info.get("grossMargins")
    profit_margin = info.get("profitMargins")
    revenue = info.get("totalRevenue")
    name = info.get("shortName", ticker)
    sector = info.get("sector", "Technology")

    if not all([gross_margin, profit_margin, revenue]) or gross_margin <= 0:
        return None

    gm_pct = gross_margin * 100
    pm_pct = profit_margin * 100
    net_income_b = (revenue * profit_margin) / 1e9

    question = (
        f"{name} ({ticker}) reports a gross margin of {gm_pct:.1f}% and a net profit margin "
        f"of {pm_pct:.1f}% on TTM revenue of ${revenue/1e9:.1f}B. "
        f"Calculate the approximate net income in billions. "
        f"Is this margin profile strong or weak for the {sector} sector?"
    )

    def check(ans: str) -> bool:
        return verify_numeric(ans, net_income_b, tolerance=0.08)

    return {
        "type": "profit_margin",
        "params": {"ticker": ticker, "gross_margin": gm_pct, "profit_margin": pm_pct, "revenue_b": revenue / 1e9},
        "expected": round(net_income_b, 2),
        "question": question,
        "answer_check": check,
        "real_data": True,
    }


# ── CLASS 3: Due Diligence Scenarios ─────────────────────────────────────────

_RISK_PROFILES = ["Conservative", "Moderate", "Aggressive"]

_SECTOR_PE_BENCHMARKS = {
    "Technology": 28, "Healthcare": 22, "Financial Services": 14,
    "Consumer Cyclical": 20, "Communication Services": 18,
    "Energy": 12, "Utilities": 16, "Consumer Defensive": 20,
    "Industrials": 20, "Basic Materials": 15, "Real Estate": 30,
}


def _gen_dd_scenario() -> Optional[dict]:
    """Generate a Due Diligence suitability assessment scenario using real yfinance data."""
    ticker = random.choice(_TICKERS)
    risk_profile = random.choice(_RISK_PROFILES)
    info = _fetch_ticker_info(ticker)
    if not info:
        return None

    # Extract key fields
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    pe = info.get("trailingPE")
    fwd_pe = info.get("forwardPE")
    mktcap = info.get("marketCap")
    dividend_yield = info.get("dividendYield", 0) or 0
    sector = info.get("sector", "Technology")
    name = info.get("shortName", ticker)
    sector_avg_pe = _SECTOR_PE_BENCHMARKS.get(sector, 20)

    if not price or not pe or pe <= 0 or pe > 500 or not mktcap:
        return None

    # Fetch news headlines
    try:
        t = yf.Ticker(ticker)
        news = t.news or []
        headlines = []
        for item in news[:3]:
            content = item.get("content") or {}
            title = content.get("title") or item.get("title") or "(no title)"
            headlines.append(title)
    except Exception:
        headlines = ["No recent news available."]

    while len(headlines) < 3:
        headlines.append("No additional news.")

    # Format market snapshot for the user message
    mktcap_b = mktcap / 1e9
    div_pct = dividend_yield * 100

    user_message = f"""Please perform a Due Diligence and Suitability Assessment for **{ticker}** \
({name}) for a **{risk_profile}** risk profile.

**Market Snapshot (via yfinance):**
- Current Price: ${price:.2f}
- Trailing P/E: {pe:.1f}x  (Sector avg: {sector_avg_pe}x — {sector})
- Forward P/E: {f'{fwd_pe:.1f}x' if fwd_pe and fwd_pe > 0 else 'N/A'}
- Market Cap: ${mktcap_b:.1f}B
- Dividend Yield: {div_pct:.2f}%
- Sector: {sector}

**Recent News Headlines:**
1. {headlines[0]}
2. {headlines[1]}
3. {headlines[2]}"""

    def check(ans: str) -> bool:
        has_thinking = "<thinking>" in ans and "</thinking>" in ans
        has_output = "<output>" in ans and "</output>" in ans
        has_verdict = "APPROVED" in ans.upper() or "REJECTED" in ans.upper()
        return has_thinking and has_output and has_verdict

    return {
        "type": "due_diligence",
        "system_prompt": SIPDO_DD_SYSTEM_PROMPT,
        "params": {
            "ticker": ticker,
            "risk_profile": risk_profile,
            "pe": pe,
            "sector_avg_pe": sector_avg_pe,
            "mktcap_b": round(mktcap_b, 1),
            "dividend_yield_pct": round(div_pct, 2),
        },
        "question": user_message,
        "answer_check": check,
        "real_data": True,
    }


# ── Scenario registry ─────────────────────────────────────────────────────────

MATH_GENERATORS = [
    _gen_kelly_scenario,
    _gen_sharpe_scenario,
    _gen_position_size_scenario,
    _gen_max_drawdown_scenario,
]

MARKET_GENERATORS = [
    _gen_pe_analysis_scenario,
    _gen_market_cap_scenario,
    _gen_52week_range_scenario,
    _gen_analyst_consensus_scenario,
    _gen_profit_margin_scenario,
]

SYSTEM_PROMPT = """You are a precise quantitative finance expert and stock analyst.
When asked a financial math or market analysis question:
1. Show your reasoning step by step.
2. Clearly state the final numeric answer or verdict.
3. Round numbers to 2-4 decimal places where appropriate.
4. Reference the specific data given — never invent numbers.
5. Do not refuse or hedge — always compute the exact answer."""

# ── CLASS 3: Due Diligence FinCoT prompt ──────────────────────────────────────

SIPDO_DD_SYSTEM_PROMPT = """You are an expert financial data generator creating training pairs \
for an institutional Due Diligence Analyst Agent.

Your task: given a simulated yfinance market snapshot and a user risk profile, generate a \
realistic training example showing correct FinCoT reasoning and a structured DD report.

STRICT OUTPUT FORMAT — you must produce exactly this structure:

<thinking>
Step 1 — Valuation check: evaluate P/E vs sector average. Is the stock cheap or expensive?
Step 2 — Size & liquidity: what does market cap tell us about risk?
Step 3 — News sentiment: do headlines suggest tailwinds or headwinds?
Step 4 — Suitability match: does this asset fit the requested risk profile?
Step 5 — Verdict justification: synthesise the above into one clear decision.
</thinking>

<output>
## Due Diligence Report — {TICKER} ({RISK_PROFILE} Profile)

**Valuation:** [2-3 sentences on P/E, forward P/E vs sector]
**Financial Health:** [2-3 sentences on market cap, dividend yield, stability]
**News Sentiment:** [1-2 sentences summarising the 3 headlines — bullish / bearish / neutral]

VERDICT: APPROVED ✓ — [one-sentence justification matched to risk profile]
   — or —
VERDICT: REJECTED ✗ — [one-sentence justification matched to risk profile]
</output>

Rules:
- Never fabricate numbers — use only the data provided in the user message.
- The verdict must logically follow from the analysis in <thinking>.
- Conservative profiles need low P/E, stable dividends, large cap, calm news.
- Aggressive profiles can tolerate high P/E, growth momentum, volatile news.
- Moderate profiles balance growth potential against stability."""


def generate_pair(client: OpenAI, model: str, scenario: dict) -> Optional[dict]:
    """Run one SIPDO iteration: generate answer + verify.

    DD scenarios use SIPDO_DD_SYSTEM_PROMPT and higher max_tokens.
    Math/market scenarios use SYSTEM_PROMPT with tight token budget.
    """
    is_dd = scenario["type"] == "due_diligence"
    system_prompt = scenario.get("system_prompt", SYSTEM_PROMPT)
    max_tokens = 1200 if is_dd else 600
    temperature = 0.3 if is_dd else 0.1  # slight creativity for report prose

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": scenario["question"]},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        answer = response.choices[0].message.content or ""

        if not scenario["answer_check"](answer):
            return None

        return {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": scenario["question"]},
                {"role": "assistant", "content": answer},
            ],
            "metadata": {
                "type": scenario["type"],
                "params": scenario.get("params", {}),
                "expected": str(scenario.get("expected", "")),
                "real_data": scenario.get("real_data", False),
                "verified": True,
                "generated_at": datetime.utcnow().isoformat(),
            },
        }
    except Exception as e:
        log(f"  [red]API error: {e}[/red]")
        return None


def main():
    parser = argparse.ArgumentParser(description="SIPDO Synthetic Financial Data Generator")
    parser.add_argument("--model", default="qwen/qwen-2.5-72b-instruct")
    parser.add_argument("--n", type=int, default=200, help="Total verified pairs to generate")
    parser.add_argument(
        "--mode",
        default="dd",
        choices=["dd", "math", "market", "all"],
        help=(
            "dd    — Due Diligence FinCoT reports only (recommended for V1 training)\n"
            "math  — Deterministic math only (Kelly, Sharpe, Drawdown, Position Sizing)\n"
            "market— Real market data Q&A only (P/E, Market Cap, etc.)\n"
            "all   — Mix of all three classes"
        ),
    )
    parser.add_argument("--market_ratio", type=float, default=0.4,
                        help="In 'all' mode: fraction from market data vs math (0.0–1.0)")
    parser.add_argument("--output", default="scripts/training/finance_qa.jsonl")
    parser.add_argument("--sleep", type=float, default=0.5)
    args = parser.parse_args()

    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY", ""),
        base_url=os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1"),
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    log(f"\n[bold]SIPDO Financial Data Generator[/bold]")
    log(f"  Model:  {args.model}")
    log(f"  Mode:   {args.mode}")
    log(f"  Target: {args.n} verified pairs")
    log(f"  Output: {output_path}\n")

    generated = 0
    attempts = 0
    failed = 0
    type_counts: dict[str, int] = {}

    # Build generator pool based on mode
    if args.mode == "dd":
        gen_pool = [_gen_dd_scenario]
    elif args.mode == "math":
        gen_pool = MATH_GENERATORS
    elif args.mode == "market":
        gen_pool = MARKET_GENERATORS if YFINANCE_AVAILABLE else MATH_GENERATORS
    else:  # all
        gen_pool = MATH_GENERATORS + (MARKET_GENERATORS if YFINANCE_AVAILABLE else []) + [_gen_dd_scenario]

    if not YFINANCE_AVAILABLE and args.mode in ("dd", "market"):
        log("[red]yfinance required for 'dd' and 'market' modes. Install it: pip install yfinance[/red]")
        return

    with open(output_path, "w", encoding="utf-8") as f:
        while generated < args.n:
            attempts += 1
            gen_fn = random.choice(gen_pool)
            scenario = gen_fn()
            if scenario is None:
                failed += 1
                continue

            pair = generate_pair(client, args.model, scenario)
            if pair:
                f.write(json.dumps(pair, ensure_ascii=False) + "\n")
                f.flush()
                generated += 1
                stype = scenario["type"]
                type_counts[stype] = type_counts.get(stype, 0) + 1
                color = "[magenta]" if stype == "due_diligence" else "[blue]" if scenario.get("real_data") else "[green]"
                log(f"  [{generated:3d}/{args.n}] ✓ {color}{stype}[/{color[1:]}]")
            else:
                failed += 1
                log(f"  [yellow]✗ Failed: {scenario['type']}[/yellow]")

            time.sleep(args.sleep)

    log(f"\n[bold green]Done![/bold green]")
    log(f"  Generated: {generated} pairs")
    for stype, count in sorted(type_counts.items()):
        log(f"    {stype}: {count}")
    log(f"  Failed:    {failed}")
    log(f"  Pass rate: {generated / max(attempts, 1) * 100:.1f}%")
    log(f"  Output:    {output_path}")


if __name__ == "__main__":
    main()
