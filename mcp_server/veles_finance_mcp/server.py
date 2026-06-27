"""Veles Finance MCP server.

Exposes institutional-grade financial analysis tools to Claude Desktop,
Cursor, Windsurf, and any other MCP-compatible client.

Install:
    uvx veles-finance-mcp

Claude Desktop config (~/.claude/claude_desktop_config.json):
    {
      "mcpServers": {
        "veles-finance": {
          "command": "uvx",
          "args": ["veles-finance-mcp"]
        }
      }
    }
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any

import yfinance as yf
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from pydantic import BaseModel, Field, field_validator

app = Server("veles-finance")

_MARKET_CAP_LABELS = [
    (1_000_000_000_000, "T"),
    (1_000_000_000, "B"),
    (1_000_000, "M"),
]


def _fmt_cap(v: float | None) -> str:
    if v is None:
        return "N/A"
    for threshold, suffix in _MARKET_CAP_LABELS:
        if abs(v) >= threshold:
            return f"${v / threshold:.2f}{suffix}"
    return f"${v:,.0f}"


def _fmt_price(v: float | None) -> str:
    return f"${v:,.2f}" if v is not None else "N/A"


def _fmt_ratio(v: float | None, d: int = 2) -> str:
    return f"{v:.{d}f}" if v is not None else "N/A"


# ── Tool: get_market_data ──────────────────────────────────────────────────────

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_market_data",
            description=(
                "Fetch live stock price, fundamentals, and recent news for any ticker. "
                "Returns current price, P/E, market cap, EPS, revenue, margins, beta, "
                "52-week range, analyst consensus, and up to 5 news headlines. "
                "Data sourced from Yahoo Finance via yfinance."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol (e.g. 'NVDA', 'AAPL', 'MSFT').",
                    }
                },
                "required": ["ticker"],
            },
        ),
        Tool(
            name="due_diligence_report",
            description=(
                "Generate an institutional-grade Due Diligence report with a mandatory "
                "APPROVED or REJECTED verdict. Automatically fetches live market data, "
                "applies FinCoT reasoning, and enforces structured output. "
                "Ideal for suitability assessments against a specific risk profile."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol (e.g. 'NVDA', 'AAPL').",
                    },
                    "risk_profile": {
                        "type": "string",
                        "enum": ["conservative", "moderate", "aggressive"],
                        "description": "Investor risk profile for suitability assessment.",
                    },
                },
                "required": ["ticker", "risk_profile"],
            },
        ),
        Tool(
            name="kelly_position_size",
            description=(
                "Calculate the mathematically optimal position size using the Kelly Criterion. "
                "Returns full Kelly, half Kelly, and quarter Kelly allocations with practical guidance."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "win_probability": {
                        "type": "number",
                        "description": "Probability of a winning trade (0.01–0.99). E.g. 0.60 for 60% win rate.",
                    },
                    "payout_ratio": {
                        "type": "number",
                        "description": "Average profit / average loss ratio. E.g. 2.0 means win $2 per $1 risked.",
                    },
                },
                "required": ["win_probability", "payout_ratio"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name == "get_market_data":
        return [TextContent(type="text", text=_get_market_data(arguments["ticker"]))]
    elif name == "due_diligence_report":
        return [TextContent(type="text", text=_due_diligence_report(
            arguments["ticker"],
            arguments["risk_profile"],
        ))]
    elif name == "kelly_position_size":
        return [TextContent(type="text", text=_kelly(
            arguments["win_probability"],
            arguments["payout_ratio"],
        ))]
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


# ── Implementations ────────────────────────────────────────────────────────────

def _get_market_data(ticker: str) -> str:
    ticker = ticker.strip().upper()
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        news = t.news or []
    except Exception as exc:
        return f"Error fetching data for {ticker}: {exc}"

    company = info.get("longName") or info.get("shortName") or ticker
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    prev = info.get("previousClose") or info.get("regularMarketPreviousClose")

    change = "N/A"
    if price and prev:
        delta = price - prev
        pct = (delta / prev) * 100
        sign = "+" if delta >= 0 else ""
        change = f"{sign}{delta:.2f} ({sign}{pct:.2f}%)"

    news_lines = []
    for i, item in enumerate(news[:5], 1):
        content = item.get("content") or {}
        title = content.get("title") or item.get("title") or "(no title)"
        provider = content.get("provider", {}).get("displayName") or item.get("publisher") or "Unknown"
        news_lines.append(f"  {i}. {title}  [{provider}]")

    return f"""
Market Data — {company} ({ticker})
═══════════════════════════════════════════════════════
Price:          {_fmt_price(price)}   Change: {change}
52W High:       {_fmt_price(info.get('fiftyTwoWeekHigh'))}
52W Low:        {_fmt_price(info.get('fiftyTwoWeekLow'))}

Fundamentals:
  Market Cap:   {_fmt_cap(info.get('marketCap'))}
  Trailing P/E: {_fmt_ratio(info.get('trailingPE'))}
  Forward P/E:  {_fmt_ratio(info.get('forwardPE'))}
  EPS (TTM):    {_fmt_ratio(info.get('trailingEps'))}
  Revenue:      {_fmt_cap(info.get('totalRevenue'))}
  Margin:       {_fmt_ratio(info.get('profitMargins', 0) * 100, 1) if info.get('profitMargins') else 'N/A'}%
  Beta:         {_fmt_ratio(info.get('beta'))}

Analyst Consensus:
  Rating:       {(info.get('recommendationKey') or 'N/A').upper()}
  Target:       {_fmt_price(info.get('targetMeanPrice'))}

Recent News:
{chr(10).join(news_lines) if news_lines else '  No recent news.'}
═══════════════════════════════════════════════════════
Source: Yahoo Finance (yfinance)
""".strip()


_THRESHOLDS = {
    "conservative": {"max_pe": 25, "max_beta": 1.0, "max_position": "5%"},
    "moderate":     {"max_pe": 35, "max_beta": 1.4, "max_position": "10%"},
    "aggressive":   {"max_pe": 60, "max_beta": 2.0, "max_position": "20%"},
}


def _due_diligence_report(ticker: str, risk_profile: str) -> str:
    ticker = ticker.strip().upper()
    profile = risk_profile.lower()
    thresholds = _THRESHOLDS.get(profile, _THRESHOLDS["moderate"])

    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
    except Exception as exc:
        return f"Error fetching data for {ticker}: {exc}"

    company = info.get("longName") or info.get("shortName") or ticker
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    pe = info.get("trailingPE")
    fwd_pe = info.get("forwardPE")
    beta = info.get("beta")
    market_cap = info.get("marketCap")
    revenue = info.get("totalRevenue")
    profit_margin = info.get("profitMargins")
    eps = info.get("trailingEps")
    high_52 = info.get("fiftyTwoWeekHigh")
    low_52 = info.get("fiftyTwoWeekLow")
    rec = (info.get("recommendationKey") or "N/A").upper().replace("_", " ")
    target = info.get("targetMeanPrice")
    dividend = info.get("dividendYield")

    # ── Verdict logic ──────────────────────────────────────────────────────────
    rejection_reasons = []
    approval_signals = []

    if pe is not None:
        if pe > thresholds["max_pe"]:
            rejection_reasons.append(f"P/E {pe:.1f}x exceeds {profile} threshold of {thresholds['max_pe']}x")
        else:
            approval_signals.append(f"P/E {pe:.1f}x is within {profile} threshold ({thresholds['max_pe']}x max)")

    if beta is not None:
        if beta > thresholds["max_beta"]:
            rejection_reasons.append(f"Beta {beta:.2f} exceeds {profile} volatility ceiling of {thresholds['max_beta']}")
        else:
            approval_signals.append(f"Beta {beta:.2f} is within {profile} volatility tolerance")

    if profit_margin is not None and profit_margin > 0.15:
        approval_signals.append(f"Strong profit margin of {profit_margin*100:.1f}%")
    elif profit_margin is not None and profit_margin < 0:
        rejection_reasons.append(f"Negative profit margin ({profit_margin*100:.1f}%)")

    if target and price and target > price * 1.15:
        approval_signals.append(f"Analyst target {_fmt_price(target)} implies {((target/price)-1)*100:.0f}% upside")

    verdict = "REJECTED" if rejection_reasons else "APPROVED"
    verdict_symbol = "✗" if verdict == "REJECTED" else "✓"
    primary_reason = rejection_reasons[0] if rejection_reasons else (approval_signals[0] if approval_signals else "meets all criteria")

    strengths = "\n".join(f"  + {s}" for s in approval_signals[:4]) or "  (insufficient data)"
    risks = "\n".join(f"  - {r}" for r in rejection_reasons[:4]) or "  (no major red flags identified)"

    return f"""
╔══════════════════════════════════════════════════════╗
║         INSTITUTIONAL DUE DILIGENCE REPORT           ║
╚══════════════════════════════════════════════════════╝

  Company:       {company} ({ticker})
  Risk Profile:  {profile.capitalize()}
  Generated:     {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}

── Market Snapshot ────────────────────────────────────
  Price:             {_fmt_price(price)}
  Market Cap:        {_fmt_cap(market_cap)}
  52-Week High:      {_fmt_price(high_52)}
  52-Week Low:       {_fmt_price(low_52)}

── Fundamentals ───────────────────────────────────────
  Trailing P/E:      {_fmt_ratio(pe)}  (threshold: {thresholds['max_pe']}x)
  Forward P/E:       {_fmt_ratio(fwd_pe)}
  EPS (TTM):         {_fmt_ratio(eps)}
  Revenue (TTM):     {_fmt_cap(revenue)}
  Profit Margin:     {_fmt_ratio(profit_margin * 100, 1) + '%' if profit_margin is not None else 'N/A'}
  Beta:              {_fmt_ratio(beta)}  (ceiling: {thresholds['max_beta']})
  Dividend Yield:    {_fmt_ratio(dividend * 100, 2) + '%' if dividend else 'None'}

── Analyst Consensus ──────────────────────────────────
  Recommendation:    {rec}
  Price Target:      {_fmt_price(target)}

── Strengths ──────────────────────────────────────────
{strengths}

── Risks ──────────────────────────────────────────────
{risks}

── Position Sizing ────────────────────────────────────
  Profile Max:       {thresholds['max_position']} of portfolio

══════════════════════════════════════════════════════
  VERDICT:  {verdict} {verdict_symbol}

  {primary_reason}
══════════════════════════════════════════════════════

Source: Yahoo Finance via yfinance · Veles Finance MCP
""".strip()


def _kelly(win_probability: float, payout_ratio: float) -> str:
    p = win_probability
    q = 1.0 - p
    b = payout_ratio

    edge = p * b - q
    if edge <= 0:
        return (
            f"Kelly Criterion — No Positive Edge\n"
            f"Expected value = {edge:.4f} (negative)\n"
            f"Kelly Criterion requires a positive expected value. "
            f"Do not risk capital on this strategy."
        )

    kelly = edge / b
    half_kelly = kelly / 2

    guidance = ""
    if kelly * 100 > 25:
        guidance = "CAUTION: Full Kelly >25% — highly aggressive. Use Half-Kelly or less."
    elif kelly * 100 > 10:
        guidance = "Moderate allocation. Half-Kelly recommended for live trading."
    else:
        guidance = "Conservative allocation. Full Kelly may be applied directly."

    return f"""
Kelly Criterion Analysis
═══════════════════════════════════════
  Win Probability:  {p:.1%}
  Payout Ratio:     {b:.2f}x
  Expected Value:   +{edge:.4f} per unit

Optimal Position Sizing:
  Full Kelly:       {kelly*100:.2f}% of capital
  Half Kelly:       {half_kelly*100:.2f}% of capital  ← recommended
  Quarter Kelly:    {kelly*100/4:.2f}% of capital

Example ($10,000 account):
  Full Kelly  → risk ${10_000 * kelly:,.2f} per trade
  Half Kelly  → risk ${10_000 * half_kelly:,.2f} per trade

{guidance}
═══════════════════════════════════════
""".strip()


def main():
    import asyncio
    asyncio.run(_run())


async def _run():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    main()
