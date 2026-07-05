"""
Trader-focused tools for Veles Finance Agent.

New tools — no model changes required:
  - compare_annual_reports : YoY 10-K comparison (revenue, margins, debt, R&D)
  - get_earnings_calendar  : Next earnings date + analyst estimates
  - screen_stocks          : Filter stocks by sector, P/E, beta, margin
"""
from __future__ import annotations
import time
from concurrent.futures import ThreadPoolExecutor
import httpx
import yfinance as yf
from datetime import date as _date
from langchain_core.tools import tool
from .sec_tool import _get_cik, HEADERS

_BASE = "https://data.sec.gov"


def yf_with_retry(fn, retries: int = 5, base_delay: float = 2.0):
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


def _fmt_m(v: float | None) -> str:
    if v is None:
        return "N/A"
    if abs(v) >= 1_000:
        return f"${v / 1_000:.2f}B"
    return f"${v:.1f}M"


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


# ── YoY 10-K Comparison ───────────────────────────────────────────────────────

_XBRL_MAP = {
    "Revenues":                                             "revenue",
    "RevenueFromContractWithCustomerExcludingAssessedTax":  "revenue",
    "RevenueFromContractWithCustomerIncludingAssessedTax":  "revenue",
    "SalesRevenueNet":                                      "revenue",
    "NetIncomeLoss":                                        "net_income",
    "GrossProfit":                                          "gross_profit",
    "CostOfRevenue":                                        "cost_of_revenue",
    "CostOfGoodsSold":                                      "cost_of_revenue",
    "CostOfGoodsAndServicesSold":                           "cost_of_revenue",
    "NetCashProvidedByUsedInOperatingActivities":           "operating_cf",
    "LongTermDebt":                                         "total_debt",
    "LongTermDebtAndCapitalLeaseObligations":               "total_debt",
    "CashAndCashEquivalentsAtCarryingValue":                "cash",
    "CashCashEquivalentsAndShortTermInvestments":           "cash",
    "ResearchAndDevelopmentExpense":                        "rd_expense",
    "CapitalExpenditureDiscontinuedOperations":             "capex",
    "PaymentsToAcquirePropertyPlantAndEquipment":           "capex",
}


def _get_two_years_xbrl(cik: str) -> tuple[dict, dict]:
    """Fetch XBRL CompanyFacts once and extract two most recent fiscal years."""
    try:
        r = httpx.get(
            f"{_BASE}/api/xbrl/companyfacts/CIK{cik}.json",
            headers=HEADERS,
            timeout=30,
        )
        facts = r.json()
    except Exception:
        return {}, {}

    us_gaap = facts.get("facts", {}).get("us-gaap", {})

    # Collect annual fiscal-year-end dates from revenue concepts
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
        for concept, field in _XBRL_MAP.items():
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

        # Derive gross_profit from cost_of_revenue if not directly available
        if "gross_profit" not in out and "cost_of_revenue" in out and "revenue" in out:
            out["gross_profit"] = round(out["revenue"] - out.pop("cost_of_revenue"), 2)
        else:
            out.pop("cost_of_revenue", None)

        # Derived margins
        if "gross_profit" in out and out.get("revenue"):
            out["gross_margin"] = round(out["gross_profit"] / out["revenue"] * 100, 1)
        if "net_income" in out and out.get("revenue"):
            out["net_margin"] = round(out["net_income"] / out["revenue"] * 100, 1)

        out["fy_end"] = target_fy
        return out

    return _extract(current_fy), _extract(prev_fy)


@tool
def compare_annual_reports(ticker: str) -> str:
    """Compare the last two annual 10-K reports to show year-over-year changes.

    Shows changes in revenue, profit margins, cash, debt, R&D and CapEx.
    Use this when the user asks what changed, how the company grew, or wants
    to spot trends between fiscal years.

    Args:
        ticker: Stock ticker symbol (e.g. 'AAPL', 'NVDA', 'TSLA')
    """
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
        chg = _pct_change(c, p)
        arr = _arrow(c, p)
        return f"  {label:<22} {p_str:>10}  →  {c_str:>10}   {chg}{arr}"

    return f"""
╔══════════════════════════════════════════════════════════════╗
║       YEAR-OVER-YEAR 10-K COMPARISON — {ticker:<6}              ║
╚══════════════════════════════════════════════════════════════╝
  Period:  {prev_fy}  →  {curr_fy}
                           {'Prior Year':>10}     {'This Year':>10}   Change

── Revenue & Profitability ────────────────────────────────────
{row('Revenue', 'revenue')}
{row('Gross Profit', 'gross_profit')}
{row('Net Income', 'net_income')}
{row('Gross Margin', 'gross_margin', is_pct=True)}
{row('Net Margin', 'net_margin', is_pct=True)}

── Cash & Debt ────────────────────────────────────────────────
{row('Operating Cash Flow', 'operating_cf')}
{row('Cash & Equivalents', 'cash')}
{row('Total Debt', 'total_debt')}

── Investment ─────────────────────────────────────────────────
{row('R&D Expense', 'rd_expense')}
{row('CapEx', 'capex')}
══════════════════════════════════════════════════════════════
Source: SEC EDGAR XBRL API
""".strip()


# ── Earnings Calendar ─────────────────────────────────────────────────────────

@tool
def get_earnings_calendar(ticker: str) -> str:
    """Get the next earnings date and analyst estimates for a stock.

    Critical for traders timing positions around earnings events.
    Shows earnings date, EPS estimates, revenue estimates, and forward P/E.

    Args:
        ticker: Stock ticker symbol (e.g. 'AAPL', 'NVDA', 'TSLA')
    """
    ticker = ticker.strip().upper()
    try:
        t = yf.Ticker(ticker)
        info = yf_with_retry(lambda: t.info) or {}
        company = info.get("longName") or info.get("shortName") or ticker

        lines = [
            f"Earnings Calendar — {company} ({ticker})",
            "═" * 54,
        ]

        # Next earnings date
        next_date = None
        try:
            cal = t.calendar
            if cal is not None:
                if hasattr(cal, "to_dict"):
                    cal_dict = cal.to_dict()
                    next_date = cal_dict.get("Earnings Date", [None])[0] if cal_dict.get("Earnings Date") else None
                elif isinstance(cal, dict):
                    next_date = cal.get("Earnings Date")
                # yfinance sometimes nests this in an extra list — unwrap it
                if isinstance(next_date, list):
                    next_date = next_date[0] if next_date else None
        except Exception:
            pass

        if next_date is None:
            ts = info.get("earningsTimestamp") or info.get("earningsDate")
            if ts:
                from datetime import datetime as _dt
                if isinstance(ts, (int, float)):
                    next_date = _dt.fromtimestamp(ts).strftime("%Y-%m-%d")
                else:
                    next_date = str(ts)

        lines.append(f"  Next Earnings Date:  {next_date or 'Not yet announced'}")

        # Current price
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
            upside = (target / price - 1) * 100
            lines.append(f"  Implied Upside:      {upside:+.1f}%")

        lines.append("═" * 54)
        return "\n".join(lines)

    except Exception as e:
        return f"Error fetching earnings calendar for {ticker}: {e}"


# ── Stock Screener ─────────────────────────────────────────────────────────────

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


@tool
def screen_stocks(
    sector: str = "tech",
    max_pe: float = 35.0,
    max_beta: float = 1.5,
    min_margin_pct: float = 10.0,
) -> str:
    """Screen stocks in a sector by financial criteria to find investment opportunities.

    Filters by P/E ratio, beta (volatility), and profit margin.
    Returns ranked list of stocks that pass all filters.

    Args:
        sector: Market sector to screen — 'tech', 'ai', 'semi', 'energy',
                'finance', 'healthcare', 'consumer', 'crypto'
        max_pe: Maximum trailing P/E ratio (default 35)
        max_beta: Maximum beta / volatility ceiling (default 1.5)
        min_margin_pct: Minimum profit margin in % (default 10.0)
    """
    sector = sector.lower().strip()
    tickers = _SECTOR_TICKERS.get(sector)
    if not tickers:
        available = ", ".join(_SECTOR_TICKERS.keys())
        return f"Unknown sector '{sector}'. Available: {available}"

    def _fetch(ticker: str) -> dict | None:
        try:
            info = yf_with_retry(lambda t=ticker: yf.Ticker(t).info) or {}
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

            upside = None
            if target and price:
                upside = (target / price - 1) * 100

            return {
                "ticker": ticker,
                "name": name,
                "price": price,
                "pe": pe,
                "beta": beta,
                "margin": margin * 100 if margin is not None else None,
                "upside": upside,
            }
        except Exception:
            return None

    # Fetch all tickers concurrently — sequential fetches with per-ticker
    # retry/backoff could take 100+ seconds for a 10-ticker sector, exceeding
    # the frontend/proxy timeout before the response ever comes back.
    with ThreadPoolExecutor(max_workers=len(tickers)) as pool:
        results = list(pool.map(_fetch, tickers))
    passed = [r for r in results if r is not None]

    if not passed:
        return (
            f"No stocks in '{sector}' passed filters "
            f"(P/E ≤ {max_pe}, Beta ≤ {max_beta}, Margin ≥ {min_margin_pct}%). "
            f"Try relaxing the criteria — e.g. increase max_pe or lower min_margin_pct."
        )

    # Sort by margin descending
    passed.sort(key=lambda x: x["margin"] or 0, reverse=True)

    lines = [
        f"Stock Screener — {sector.upper()}",
        f"Filters: P/E ≤ {max_pe} | Beta ≤ {max_beta} | Margin ≥ {min_margin_pct}%",
        "═" * 70,
        f"  {'#':<3} {'Ticker':<7} {'Name':<21} {'Price':>8} {'P/E':>7} {'Beta':>6} {'Margin':>8} {'Upside':>8}",
        "  " + "─" * 64,
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

    lines.append("═" * 70)
    lines.append(f"  {len(passed)} of {len(tickers)} stocks passed | Source: Yahoo Finance")
    return "\n".join(lines)
