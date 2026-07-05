from __future__ import annotations
from datetime import datetime
import os
import httpx
import yfinance as yf
from langchain_core.tools import tool
from .sec_tool import fetch_sec_10k_tool
from .trader_tools import compare_annual_reports, get_earnings_calendar, screen_stocks, yf_with_retry

_NBU_URL = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange"
_FINNHUB_URL = "https://finnhub.io/api/v1/quote"
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")


def _finnhub_quote(ticker: str) -> str | None:
    """Last-resort price-only fallback via Finnhub's free tier, used only when
    yfinance (both .info and fast_info) fails — e.g. Yahoo IP rate limiting.
    Returns None if no FINNHUB_API_KEY is configured or the call fails, so
    callers can fall through to the generic error message."""
    if not FINNHUB_API_KEY:
        return None
    try:
        resp = httpx.get(_FINNHUB_URL, params={"symbol": ticker, "token": FINNHUB_API_KEY}, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    price = data.get("c")  # current price
    prev = data.get("pc")  # previous close
    if not price:
        return None

    change = ""
    if prev:
        delta = price - prev
        pct = (delta / prev) * 100 if prev else 0
        sign = "+" if delta >= 0 else ""
        change = f"  Change: {sign}{delta:.2f} ({sign}{pct:.2f}%)"
    return f"Market Data — {ticker} (partial — fundamentals unavailable, via Finnhub fallback)\nPrice: {_fmt_price(price)}{change}"

# ISO codes NBU actually publishes a rate for — used to catch cases where the
# orchestrator passes a currency code (or FX pair like "USDUAH") into
# get_market_data instead of calling get_fx_rate, despite the system prompt
# telling it not to. Small orchestrator models don't always follow that rule,
# so this redirects at the tool level instead of trusting instruction-following.
_KNOWN_CURRENCY_CODES = {
    "USD", "EUR", "GBP", "PLN", "CHF", "JPY", "CAD", "AUD", "CNY", "CZK",
    "HUF", "TRY", "SEK", "NOK", "DKK", "ILS", "GEL", "KZT",
}


def _fetch_nbu_rate(code: str) -> str:
    try:
        resp = httpx.get(_NBU_URL, params={"valcode": code, "json": ""}, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return f"Error fetching FX rate for {code}: {exc}"

    if not data:
        return f"No NBU rate found for currency code '{code}'. Check the code is a valid 3-letter ISO code (e.g. USD, EUR, PLN)."

    entry = data[0]
    return (
        f"NBU official rate — {entry.get('txt', code)} ({code}): "
        f"{entry['rate']:.4f} UAH as of {entry.get('exchangedate', 'today')}"
    )


def _as_currency_redirect(ticker: str) -> str | None:
    """Return an NBU rate string if `ticker` looks like a currency code or FX
    pair rather than a stock ticker, else None."""
    if ticker in _KNOWN_CURRENCY_CODES:
        return _fetch_nbu_rate(ticker)
    if len(ticker) == 6 and ticker[:3] in _KNOWN_CURRENCY_CODES:
        return _fetch_nbu_rate(ticker[:3])
    return None


_MARKET_CAP_LABELS = [(1_000_000_000_000, "T"), (1_000_000_000, "B"), (1_000_000, "M")]

def _fmt_cap(v):
    if v is None: return "N/A"
    for threshold, suffix in _MARKET_CAP_LABELS:
        if abs(v) >= threshold:
            return f"${v / threshold:.2f}{suffix}"
    return f"${v:,.0f}"

def _fmt_price(v): return f"${v:,.2f}" if v is not None else "N/A"
def _fmt_ratio(v, d=2): return f"{v:.{d}f}" if v is not None else "N/A"


@tool
def get_market_data(ticker: str) -> str:
    """Fetch live stock price, fundamentals, and recent news for any ticker symbol."""
    ticker = ticker.strip().upper()

    redirect = _as_currency_redirect(ticker)
    if redirect is not None:
        return redirect

    try:
        t = yf.Ticker(ticker)
        info = yf_with_retry(lambda: t.info) or {}
    except Exception as exc:
        # Yahoo's full quoteSummary endpoint (behind .info) rate-limits harder
        # than fast_info's lighter endpoint. fast_info won't have fundamentals
        # (P/E, margin, etc.) but at least returns price when .info is blocked.
        try:
            fi = t.fast_info
            price = fi.get("lastPrice")
            prev = fi.get("previousClose")
            if price is None:
                raise exc
            change = ""
            if prev:
                delta = price - prev
                pct = (delta / prev) * 100
                sign = "+" if delta >= 0 else ""
                change = f"  Change: {sign}{delta:.2f} ({sign}{pct:.2f}%)"
            return (
                f"Market Data — {ticker} (partial — fundamentals unavailable, Yahoo rate-limited)\n"
                f"Price: {_fmt_price(price)}{change}"
            )
        except Exception:
            pass

        finnhub_result = _finnhub_quote(ticker)
        if finnhub_result:
            return finnhub_result

        return f"Error fetching data for {ticker}: {exc}"

    # News is a nice-to-have — a Yahoo rate limit on this call alone
    # shouldn't discard the price/fundamentals we already fetched above.
    try:
        news = yf_with_retry(lambda: t.news) or []
    except Exception:
        news = []

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
""".strip()


@tool
def get_fx_rate(currency: str) -> str:
    """Fetch the official NBU (National Bank of Ukraine) exchange rate for a currency vs UAH.

    Args:
        currency: 3-letter ISO currency code, e.g. 'USD', 'EUR', 'PLN', 'GBP'
    """
    code = currency.strip().upper()
    try:
        resp = httpx.get(_NBU_URL, params={"valcode": code, "json": ""}, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return f"Error fetching FX rate for {code}: {exc}"

    if not data:
        return f"No NBU rate found for currency code '{code}'. Check the code is a valid 3-letter ISO code (e.g. USD, EUR, PLN)."

    entry = data[0]
    return (
        f"NBU official rate — {entry.get('txt', code)} ({code}): "
        f"{entry['rate']:.4f} UAH as of {entry.get('exchangedate', 'today')}"
    )


_THRESHOLDS = {
    "conservative": {"max_pe": 25, "max_beta": 1.0, "max_position": "5%"},
    "moderate":     {"max_pe": 35, "max_beta": 1.4, "max_position": "10%"},
    "aggressive":   {"max_pe": 60, "max_beta": 2.0, "max_position": "20%"},
}


@tool
def due_diligence_report(ticker: str, risk_profile: str) -> str:
    """Generate an institutional Due Diligence report with APPROVED or REJECTED verdict.

    Args:
        ticker: Stock ticker symbol (e.g. 'NVDA', 'AAPL')
        risk_profile: One of 'conservative', 'moderate', or 'aggressive'
    """
    ticker = ticker.strip().upper()
    profile = risk_profile.lower()
    thresholds = _THRESHOLDS.get(profile, _THRESHOLDS["moderate"])

    try:
        t = yf.Ticker(ticker)
        info = yf_with_retry(lambda: t.info) or {}
    except Exception as exc:
        return f"Error fetching data for {ticker}: {exc}"

    company = info.get("longName") or info.get("shortName") or ticker
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    pe = info.get("trailingPE")
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
    fwd_pe = info.get("forwardPE")

    rejection_reasons = []
    approval_signals = []

    if pe is not None:
        if pe > thresholds["max_pe"]:
            rejection_reasons.append(f"P/E {pe:.1f}x exceeds {profile} threshold of {thresholds['max_pe']}x")
        else:
            approval_signals.append(f"P/E {pe:.1f}x within {profile} threshold ({thresholds['max_pe']}x max)")

    if beta is not None:
        if beta > thresholds["max_beta"]:
            rejection_reasons.append(f"Beta {beta:.2f} exceeds {profile} ceiling of {thresholds['max_beta']}")
        else:
            approval_signals.append(f"Beta {beta:.2f} within {profile} volatility tolerance")

    if profit_margin is not None and profit_margin > 0.15:
        approval_signals.append(f"Strong profit margin {profit_margin*100:.1f}%")
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
  52W High/Low:      {_fmt_price(high_52)} / {_fmt_price(low_52)}

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
""".strip()


@tool
def kelly_position_size(win_probability: float, payout_ratio: float) -> str:
    """Calculate optimal position size using the Kelly Criterion.

    Args:
        win_probability: Probability of winning (0.01-0.99), e.g. 0.60 for 60%
        payout_ratio: Average profit / average loss ratio, e.g. 2.0 means win $2 per $1 risked
    """
    p = win_probability
    q = 1.0 - p
    b = payout_ratio
    edge = p * b - q

    if edge <= 0:
        return f"Kelly Criterion — No Positive Edge\nExpected value = {edge:.4f} (negative)\nDo not risk capital on this strategy."

    kelly = edge / b
    half_kelly = kelly / 2

    if kelly * 100 > 25:
        guidance = "CAUTION: Full Kelly >25% — use Half-Kelly or less."
    elif kelly * 100 > 10:
        guidance = "Moderate. Half-Kelly recommended for live trading."
    else:
        guidance = "Conservative. Full Kelly may be applied directly."

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

{guidance}
═══════════════════════════════════════
""".strip()


TOOLS = [
    get_market_data,
    due_diligence_report,
    kelly_position_size,
    fetch_sec_10k_tool,
    compare_annual_reports,
    get_earnings_calendar,
    screen_stocks,
    get_fx_rate,
]
