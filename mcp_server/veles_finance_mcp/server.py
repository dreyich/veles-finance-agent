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
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date as _date
from datetime import datetime
from enum import Enum
from typing import Any

import httpx
import yfinance as yf
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from pydantic import BaseModel, Field, field_validator

app = Server("veles-finance")

_SEC_HEADERS = {"User-Agent": "Veles Finance Agent contact@veles.ai"}
_SEC_BASE = "https://data.sec.gov"


def _yf_with_retry(fn, retries: int = 3, base_delay: float = 1.5):
    """Run a yfinance call with exponential backoff on transient errors (Yahoo 429 rate limits)."""
    last_exc = None
    for attempt in range(retries):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(base_delay * (2 ** attempt))
    raise last_exc

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
        Tool(
            name="fetch_sec_10k_tool",
            description=(
                "Fetch the latest SEC 10-K annual report for a company and extract key "
                "financial data (revenue, net income, margins, cash, debt) via the SEC "
                "EDGAR XBRL CompanyFacts API — structured government data, no HTML parsing."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol (e.g. 'AAPL', 'NVDA', 'MSFT').",
                    }
                },
                "required": ["ticker"],
            },
        ),
        Tool(
            name="compare_annual_reports",
            description=(
                "Compare the last two annual 10-K reports to show year-over-year changes "
                "in revenue, margins, cash, debt, R&D and CapEx. Use for 'what changed' or "
                "trend questions."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol (e.g. 'AAPL', 'NVDA', 'TSLA').",
                    }
                },
                "required": ["ticker"],
            },
        ),
        Tool(
            name="get_earnings_calendar",
            description=(
                "Get the next earnings date and analyst estimates (EPS, revenue growth, "
                "forward P/E, price target) for a stock."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol (e.g. 'AAPL', 'NVDA', 'TSLA').",
                    }
                },
                "required": ["ticker"],
            },
        ),
        Tool(
            name="screen_stocks",
            description=(
                "Screen stocks in a sector by P/E, beta, and profit margin to find "
                "investment opportunities. Available sectors: tech, ai, semi, energy, "
                "finance, healthcare, consumer, crypto."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "sector": {
                        "type": "string",
                        "enum": ["tech", "ai", "semi", "energy", "finance", "healthcare", "consumer", "crypto"],
                        "description": "Market sector to screen.",
                    },
                    "max_pe": {"type": "number", "description": "Maximum trailing P/E ratio (default 35)."},
                    "max_beta": {"type": "number", "description": "Maximum beta / volatility ceiling (default 1.5)."},
                    "min_margin_pct": {"type": "number", "description": "Minimum profit margin in % (default 10.0)."},
                },
                "required": ["sector"],
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
    elif name == "fetch_sec_10k_tool":
        return [TextContent(type="text", text=_fetch_sec_10k(arguments["ticker"]))]
    elif name == "compare_annual_reports":
        return [TextContent(type="text", text=_compare_annual_reports(arguments["ticker"]))]
    elif name == "get_earnings_calendar":
        return [TextContent(type="text", text=_get_earnings_calendar(arguments["ticker"]))]
    elif name == "screen_stocks":
        return [TextContent(type="text", text=_screen_stocks(
            arguments.get("sector", "tech"),
            arguments.get("max_pe", 35.0),
            arguments.get("max_beta", 1.5),
            arguments.get("min_margin_pct", 10.0),
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


# ── SEC EDGAR helpers (shared by fetch_sec_10k_tool and compare_annual_reports) ─

def _get_cik(ticker: str) -> str | None:
    """Map ticker -> CIK using SEC's company_tickers.json."""
    try:
        r = httpx.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers=_SEC_HEADERS, timeout=15,
        )
        data = r.json()
        ticker_upper = ticker.upper().replace("-", "")
        for entry in data.values():
            if entry["ticker"].upper() == ticker_upper:
                return str(entry["cik_str"]).zfill(10)
    except Exception:
        return None
    return None


def _get_latest_10k(cik: str) -> dict | None:
    """Return accession number and filing date of the most recent 10-K."""
    try:
        r = httpx.get(
            f"{_SEC_BASE}/submissions/CIK{cik}.json",
            headers=_SEC_HEADERS, timeout=15,
        )
        subs = r.json()
        company_name = subs.get("name", "")
        filings = subs.get("filings", {}).get("recent", {})
        forms = filings.get("form", [])
        dates = filings.get("filingDate", [])
        accessions = filings.get("accessionNumber", [])
        for i, form in enumerate(forms):
            if form == "10-K":
                return {
                    "accession": accessions[i].replace("-", ""),
                    "accession_fmt": accessions[i],
                    "date": dates[i],
                    "cik": cik,
                    "company_name": company_name,
                }
    except Exception:
        pass
    return None


_XBRL_MAP = {
    "Revenues":                                             "total_revenue",
    "RevenueFromContractWithCustomerExcludingAssessedTax":   "total_revenue",
    "RevenueFromContractWithCustomerIncludingAssessedTax":   "total_revenue",
    "SalesRevenueNet":                                       "total_revenue",
    "NetIncomeLoss":                                         "net_income",
    "Assets":                                                "total_assets",
    "LongTermDebt":                                          "total_debt",
    "LongTermDebtAndCapitalLeaseObligations":                "total_debt",
    "DebtCurrent":                                           "debt_current",
    "CashAndCashEquivalentsAtCarryingValue":                 "cash_and_equivalents",
    "CashCashEquivalentsAndShortTermInvestments":            "cash_and_equivalents",
    "NetCashProvidedByUsedInOperatingActivities":            "operating_cash_flow",
    "GrossProfit":                                           "gross_profit",
    "CostOfRevenue":                                         "cost_of_revenue",
    "CostOfGoodsSold":                                       "cost_of_revenue",
    "CostOfGoodsAndServicesSold":                            "cost_of_revenue",
    "EarningsPerShareDiluted":                               "eps_diluted",
    "CommonStockSharesOutstanding":                          "shares_outstanding",
    "StockholdersEquity":                                    "stockholders_equity",
}


def _get_xbrl_facts(cik: str) -> dict:
    """Fetch structured financial data via XBRL CompanyFacts API (most recent fiscal year)."""
    try:
        r = httpx.get(
            f"{_SEC_BASE}/api/xbrl/companyfacts/CIK{cik}.json",
            headers=_SEC_HEADERS, timeout=30,
        )
        facts = r.json()
    except Exception:
        return {}

    us_gaap = facts.get("facts", {}).get("us-gaap", {})

    _REV_CONCEPTS = (
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    )
    target_end: str | None = None
    for rev_concept in _REV_CONCEPTS:
        if rev_concept not in us_gaap:
            continue
        entries = us_gaap[rev_concept].get("units", {}).get("USD", [])
        annual = [e for e in entries if e.get("form") == "10-K" and e.get("end") and e.get("val") is not None]
        if annual:
            annual.sort(key=lambda e: e["end"], reverse=True)
            candidate = annual[0]["end"]
            if target_end is None or candidate > target_end:
                target_end = candidate

    def _value_for_period(concept_data: dict, unit_key: str, target: str | None) -> float | None:
        entries = concept_data.get("units", {}).get(unit_key, [])
        annual = [e for e in entries if e.get("form") == "10-K" and e.get("end") and e.get("val") is not None]
        if not annual:
            return None
        annual.sort(key=lambda e: e["end"], reverse=True)
        t_date = _date.fromisoformat(target) if target else None

        def _is_full_year(e: dict) -> bool:
            start = e.get("start")
            if not start:
                return True
            try:
                days = (_date.fromisoformat(e["end"]) - _date.fromisoformat(start)).days
                return 300 <= days <= 400
            except Exception:
                return True

        def _date_ok(e: dict) -> bool:
            if not t_date:
                return True
            try:
                e_date = _date.fromisoformat(e["end"])
                return abs((e_date - t_date).days) <= 365
            except Exception:
                return False

        for e in annual:
            if _is_full_year(e) and e.get("end") == target:
                return e["val"] / 1_000_000
        for e in annual:
            if _is_full_year(e) and _date_ok(e):
                return e["val"] / 1_000_000
        for e in annual:
            if _date_ok(e):
                return e["val"] / 1_000_000
        return None

    result: dict = {}
    for xbrl_name, field in _XBRL_MAP.items():
        if xbrl_name not in us_gaap or field in result:
            continue
        concept = us_gaap[xbrl_name]
        units = concept.get("units", {})
        unit_key = None
        for uk in ("USD/shares", "USD", "shares"):
            if uk in units:
                unit_key = uk
                break
        if not unit_key:
            continue
        val = _value_for_period(concept, unit_key, target_end)
        if val is None:
            continue
        if unit_key == "USD/shares":
            entry_vals = [
                e["val"] for e in concept["units"][unit_key]
                if e.get("form") == "10-K" and e.get("end") == target_end and e.get("val") is not None
            ]
            val = entry_vals[0] if entry_vals else val * 1_000_000
        result[field] = round(val, 4) if unit_key == "USD/shares" else round(val, 2)

    if "gross_profit" not in result and "cost_of_revenue" in result and "total_revenue" in result:
        result["gross_profit"] = round(result["total_revenue"] - result.pop("cost_of_revenue"), 2)
    else:
        result.pop("cost_of_revenue", None)

    if "gross_profit" in result and result.get("total_revenue"):
        result["gross_margin_pct"] = round(result["gross_profit"] / result["total_revenue"] * 100, 1)
    if "net_income" in result and result.get("total_revenue"):
        result["net_margin_pct"] = round(result["net_income"] / result["total_revenue"] * 100, 1)

    if "debt_current" in result and "total_debt" in result:
        result["total_debt"] = round(result["total_debt"] + result.pop("debt_current"), 2)
    elif "debt_current" in result:
        result["total_debt"] = result.pop("debt_current")

    result["fiscal_year_end"] = target_end
    return result


def _fmt_m(v: float | None) -> str:
    if v is None:
        return "N/A"
    if abs(v) >= 1_000:
        return f"${v / 1_000:.2f}B"
    return f"${v:.1f}M"


def _fetch_sec_10k(ticker: str) -> str:
    """Numeric-only 10-K extraction via SEC EDGAR XBRL (no qualitative risk/outlook
    analysis — that step requires the fine-tuned Veles model, which isn't available
    to this standalone MCP package)."""
    ticker = ticker.strip().upper()
    cik = _get_cik(ticker)
    if not cik:
        return f"Cannot find SEC data for {ticker}. Check the ticker symbol."

    filing = _get_latest_10k(cik)
    if not filing:
        return f"No 10-K filing found for {ticker}."

    fin = _get_xbrl_facts(cik)
    if not fin:
        return f"No XBRL data available for {ticker}."

    edgar_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=10-K"
    return f"""
SEC 10-K Report — {ticker}
Filing date: {filing['date']} | Source: {edgar_url}
══════════════════════════════════════════════════
Financial Highlights (from annual report):
  Revenue:              {_fmt_m(fin.get('total_revenue'))}
  Gross Profit:         {_fmt_m(fin.get('gross_profit'))}  ({fin.get('gross_margin_pct', 'N/A')}% margin)
  Net Income:           {_fmt_m(fin.get('net_income'))}  ({fin.get('net_margin_pct', 'N/A')}% margin)
  Operating Cash Flow:  {_fmt_m(fin.get('operating_cash_flow'))}
  Cash & Equivalents:   {_fmt_m(fin.get('cash_and_equivalents'))}
  Total Debt:           {_fmt_m(fin.get('total_debt'))}
  Total Assets:         {_fmt_m(fin.get('total_assets'))}
  EPS (diluted):        {fin.get('eps_diluted', 'N/A')}
══════════════════════════════════════════════════
Source: SEC EDGAR XBRL API
""".strip()


_COMPARE_XBRL_MAP = {
    "Revenues":                                             "revenue",
    "RevenueFromContractWithCustomerExcludingAssessedTax":   "revenue",
    "RevenueFromContractWithCustomerIncludingAssessedTax":   "revenue",
    "SalesRevenueNet":                                       "revenue",
    "NetIncomeLoss":                                         "net_income",
    "GrossProfit":                                           "gross_profit",
    "CostOfRevenue":                                         "cost_of_revenue",
    "CostOfGoodsSold":                                       "cost_of_revenue",
    "CostOfGoodsAndServicesSold":                            "cost_of_revenue",
    "NetCashProvidedByUsedInOperatingActivities":            "operating_cf",
    "LongTermDebt":                                          "total_debt",
    "LongTermDebtAndCapitalLeaseObligations":                "total_debt",
    "CashAndCashEquivalentsAtCarryingValue":                 "cash",
    "CashCashEquivalentsAndShortTermInvestments":            "cash",
    "ResearchAndDevelopmentExpense":                         "rd_expense",
    "CapitalExpenditureDiscontinuedOperations":              "capex",
    "PaymentsToAcquirePropertyPlantAndEquipment":            "capex",
}


def _get_two_years_xbrl(cik: str) -> tuple[dict, dict]:
    try:
        r = httpx.get(
            f"{_SEC_BASE}/api/xbrl/companyfacts/CIK{cik}.json",
            headers=_SEC_HEADERS, timeout=30,
        )
        facts = r.json()
    except Exception:
        return {}, {}

    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    fy_dates: set[str] = set()
    for concept in ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"):
        if concept not in us_gaap:
            continue
        for e in us_gaap[concept].get("units", {}).get("USD", []):
            if e.get("form") != "10-K" or not e.get("end"):
                continue
            start = e.get("start")
            if start:
                try:
                    days = (_date.fromisoformat(e["end"]) - _date.fromisoformat(start)).days
                    if 300 <= days <= 400:
                        fy_dates.add(e["end"])
                except Exception:
                    pass

    sorted_fy = sorted(fy_dates, reverse=True)
    if not sorted_fy:
        return {}, {}
    current_fy = sorted_fy[0]
    prev_fy = sorted_fy[1] if len(sorted_fy) > 1 else None

    def _extract(target_fy: str | None) -> dict:
        if not target_fy:
            return {}
        out: dict = {}
        for concept, field in _COMPARE_XBRL_MAP.items():
            if concept not in us_gaap or field in out:
                continue
            for e in us_gaap[concept].get("units", {}).get("USD", []):
                if e.get("form") != "10-K" or e.get("end") != target_fy:
                    continue
                if e.get("val") is None:
                    continue
                start = e.get("start")
                if start:
                    try:
                        days = (_date.fromisoformat(e["end"]) - _date.fromisoformat(start)).days
                        if not (300 <= days <= 400):
                            continue
                    except Exception:
                        pass
                out[field] = round(e["val"] / 1_000_000, 2)
                break

        if "gross_profit" not in out and "cost_of_revenue" in out and "revenue" in out:
            out["gross_profit"] = round(out["revenue"] - out.pop("cost_of_revenue"), 2)
        else:
            out.pop("cost_of_revenue", None)

        if "gross_profit" in out and out.get("revenue"):
            out["gross_margin"] = round(out["gross_profit"] / out["revenue"] * 100, 1)
        if "net_income" in out and out.get("revenue"):
            out["net_margin"] = round(out["net_income"] / out["revenue"] * 100, 1)

        out["fy_end"] = target_fy
        return out

    return _extract(current_fy), _extract(prev_fy)


def _pct_change(curr: float | None, prev: float | None) -> str:
    if curr is None or prev is None or prev == 0:
        return "N/A"
    pct = (curr - prev) / abs(prev) * 100
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.1f}%"


def _arrow(curr: float | None, prev: float | None) -> str:
    if curr is None or prev is None:
        return ""
    return " ▲" if curr > prev else " ▼"


def _compare_annual_reports(ticker: str) -> str:
    ticker = ticker.strip().upper()
    cik = _get_cik(ticker)
    if not cik:
        return f"Cannot find SEC data for {ticker}. Check the ticker symbol."

    curr, prev = _get_two_years_xbrl(cik)
    if not curr:
        return f"No XBRL data available for {ticker}."

    curr_fy = curr.get("fy_end", "Current Year")
    prev_fy = prev.get("fy_end", "Prior Year") if prev else "N/A"

    def row(label: str, field: str, is_pct: bool = False) -> str:
        c = curr.get(field)
        p = prev.get(field) if prev else None
        if is_pct:
            c_str = f"{c:.1f}%" if c is not None else "N/A"
            p_str = f"{p:.1f}%" if p is not None else "N/A"
        else:
            c_str = _fmt_m(c)
            p_str = _fmt_m(p)
        return f"  {label:<22} {p_str:>10}  ->  {c_str:>10}   {_pct_change(c, p)}{_arrow(c, p)}"

    return f"""
YEAR-OVER-YEAR 10-K COMPARISON — {ticker}
Period: {prev_fy} -> {curr_fy}

Revenue & Profitability:
{row('Revenue', 'revenue')}
{row('Gross Profit', 'gross_profit')}
{row('Net Income', 'net_income')}
{row('Gross Margin', 'gross_margin', is_pct=True)}
{row('Net Margin', 'net_margin', is_pct=True)}

Cash & Debt:
{row('Operating Cash Flow', 'operating_cf')}
{row('Cash & Equivalents', 'cash')}
{row('Total Debt', 'total_debt')}

Investment:
{row('R&D Expense', 'rd_expense')}
{row('CapEx', 'capex')}

Source: SEC EDGAR XBRL API
""".strip()


def _get_earnings_calendar(ticker: str) -> str:
    ticker = ticker.strip().upper()
    try:
        t = yf.Ticker(ticker)
        info = _yf_with_retry(lambda: t.info) or {}
        company = info.get("longName") or info.get("shortName") or ticker

        lines = [f"Earnings Calendar — {company} ({ticker})", "=" * 54]

        next_date = None
        try:
            cal = t.calendar
            if cal is not None:
                if hasattr(cal, "to_dict"):
                    cal_dict = cal.to_dict()
                    next_date = cal_dict.get("Earnings Date", [None])[0] if cal_dict.get("Earnings Date") else None
                elif isinstance(cal, dict):
                    next_date = cal.get("Earnings Date")
                if isinstance(next_date, list):
                    next_date = next_date[0] if next_date else None
        except Exception:
            pass

        if next_date is None:
            ts = info.get("earningsTimestamp") or info.get("earningsDate")
            if ts:
                if isinstance(ts, (int, float)):
                    next_date = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                else:
                    next_date = str(ts)

        lines.append(f"  Next Earnings Date:  {next_date or 'Not yet announced'}")

        price = info.get("currentPrice") or info.get("regularMarketPrice")
        lines.append(f"  Current Price:       ${price:,.2f}" if price else "  Current Price:       N/A")

        lines.append("")
        lines.append("Analyst Estimates:")
        eps_fwd = info.get("epsForward")
        eps_curr = info.get("epsCurrentYear")
        rev_growth = info.get("revenueGrowth")
        fwd_pe = info.get("forwardPE")
        peg = info.get("pegRatio")
        target = info.get("targetMeanPrice")
        rec = (info.get("recommendationKey") or "").upper().replace("_", " ")

        lines.append(f"  Forward EPS:         ${eps_fwd:.2f}" if eps_fwd else "  Forward EPS:         N/A")
        lines.append(f"  EPS (current yr):    ${eps_curr:.2f}" if eps_curr else "  EPS (current yr):    N/A")
        lines.append(f"  Forward P/E:         {fwd_pe:.1f}x" if fwd_pe else "  Forward P/E:         N/A")
        lines.append(f"  PEG Ratio:           {peg:.2f}" if peg else "  PEG Ratio:           N/A")
        lines.append(f"  Revenue Growth YoY:  {rev_growth*100:+.1f}%" if rev_growth else "  Revenue Growth YoY:  N/A")

        lines.append("")
        lines.append("Analyst Consensus:")
        lines.append(f"  Rating:              {rec or 'N/A'}")
        lines.append(f"  Price Target:        ${target:,.2f}" if target else "  Price Target:        N/A")
        if target and price:
            lines.append(f"  Implied Upside:      {(target / price - 1) * 100:+.1f}%")

        lines.append("=" * 54)
        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching earnings calendar for {ticker}: {e}"


_SECTOR_TICKERS: dict[str, list[str]] = {
    "tech":       ["AAPL", "MSFT", "GOOGL", "META", "NVDA", "AMD", "CRM", "ADBE", "ORCL", "INTC"],
    "ai":         ["NVDA", "AMD", "MSFT", "GOOGL", "META", "PLTR", "SOUN", "BBAI", "AI", "IONQ"],
    "semi":       ["NVDA", "AMD", "INTC", "QCOM", "AVGO", "MU", "AMAT", "KLAC", "LRCX", "TSM"],
    "energy":     ["XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "HAL", "OXY"],
    "finance":    ["JPM", "BAC", "WFC", "GS", "MS", "BLK", "C", "AXP", "USB", "PNC"],
    "healthcare": ["JNJ", "UNH", "PFE", "MRK", "ABT", "TMO", "DHR", "BMY", "AMGN", "GILD"],
    "consumer":   ["AMZN", "TSLA", "HD", "NKE", "MCD", "SBUX", "TGT", "COST", "WMT", "LOW"],
    "crypto":     ["COIN", "MSTR", "RIOT", "MARA", "CLSK", "BTBT", "HUT", "CIFR"],
}


def _screen_stocks(sector: str, max_pe: float, max_beta: float, min_margin_pct: float) -> str:
    sector = sector.lower().strip()
    tickers = _SECTOR_TICKERS.get(sector)
    if not tickers:
        available = ", ".join(_SECTOR_TICKERS.keys())
        return f"Unknown sector '{sector}'. Available: {available}"

    def _fetch(ticker: str) -> dict | None:
        try:
            info = _yf_with_retry(lambda t=ticker: yf.Ticker(t).info) or {}
            pe = info.get("trailingPE")
            beta = info.get("beta")
            margin = info.get("profitMargins")
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            name = (info.get("shortName") or ticker)[:20]
            target = info.get("targetMeanPrice")

            if margin is not None and margin < 0:
                return None
            if pe is not None and pe > max_pe:
                return None
            if beta is not None and beta > max_beta:
                return None
            if margin is not None and margin * 100 < min_margin_pct:
                return None

            upside = (target / price - 1) * 100 if target and price else None
            return {
                "ticker": ticker, "name": name, "price": price, "pe": pe,
                "beta": beta, "margin": margin * 100 if margin is not None else None,
                "upside": upside,
            }
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=len(tickers)) as pool:
        results = list(pool.map(_fetch, tickers))
    passed = [r for r in results if r is not None]

    if not passed:
        return (
            f"No stocks in '{sector}' passed filters "
            f"(P/E <= {max_pe}, Beta <= {max_beta}, Margin >= {min_margin_pct}%). "
            f"Try relaxing the criteria."
        )

    passed.sort(key=lambda x: x["margin"] or 0, reverse=True)

    lines = [
        f"Stock Screener — {sector.upper()}",
        f"Filters: P/E <= {max_pe} | Beta <= {max_beta} | Margin >= {min_margin_pct}%",
        "=" * 70,
        f"  {'#':<3} {'Ticker':<7} {'Name':<21} {'Price':>8} {'P/E':>7} {'Beta':>6} {'Margin':>8} {'Upside':>8}",
    ]
    for i, r in enumerate(passed[:10], 1):
        pe_str     = f"{r['pe']:.1f}x"    if r["pe"]     is not None else "N/A"
        beta_str   = f"{r['beta']:.2f}"   if r["beta"]   is not None else "N/A"
        margin_str = f"{r['margin']:.1f}%" if r["margin"] is not None else "N/A"
        price_str  = f"${r['price']:,.2f}" if r["price"]  is not None else "N/A"
        upside_str = f"{r['upside']:+.0f}%" if r["upside"] is not None else "N/A"
        lines.append(
            f"  {i:<3} {r['ticker']:<7} {r['name']:<21} {price_str:>8} "
            f"{pe_str:>7} {beta_str:>6} {margin_str:>8} {upside_str:>8}"
        )
    lines.append(f"\n  {len(passed)} of {len(tickers)} stocks passed | Source: Yahoo Finance")
    return "\n".join(lines)


def main():
    import asyncio
    asyncio.run(_run())


async def _run():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    main()
