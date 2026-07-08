from __future__ import annotations
from datetime import datetime
import os
import httpx
import yfinance as yf
from langchain_core.tools import tool
from .sec_tool import fetch_sec_10k_tool
from .trader_tools import compare_annual_reports, get_earnings_calendar, screen_stocks, yf_with_retry

_NBU_URL = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange"
_FINNHUB_QUOTE_URL = "https://finnhub.io/api/v1/quote"
_FINNHUB_PROFILE_URL = "https://finnhub.io/api/v1/stock/profile2"
_FINNHUB_METRIC_URL = "https://finnhub.io/api/v1/stock/metric"
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")


def _finnhub_get(url: str, ticker: str, extra_params: dict | None = None) -> dict | None:
    try:
        # Finnhub compresses responses with zstd by default; the zstandard
        # decoder in this environment fails on it ("Allocation error: not
        # enough memory") even for a tiny JSON payload. Requesting gzip
        # instead avoids that decode path entirely.
        resp = httpx.get(
            url,
            params={"symbol": ticker, "token": FINNHUB_API_KEY, **(extra_params or {})},
            headers={"Accept-Encoding": "gzip, deflate"},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        print(f"finnhub_call_failed url={url} ticker={ticker} error={exc}")
        return None


def _finnhub_info_dict(ticker: str) -> dict | None:
    """Same Finnhub data as _finnhub_quote, shaped as a yfinance-style `info`
    dict (same key names) so callers that build a report from `info.get(...)`
    can use either source without duplicating logic. Returns None if even the
    price is unavailable — a report needs at least that."""
    if not FINNHUB_API_KEY:
        return None
    quote = _finnhub_get(_FINNHUB_QUOTE_URL, ticker)
    if not quote or not quote.get("c"):
        return None
    profile = _finnhub_get(_FINNHUB_PROFILE_URL, ticker) or {}
    metrics = (_finnhub_get(_FINNHUB_METRIC_URL, ticker, {"metric": "all"}) or {}).get("metric", {})

    shares_millions = profile.get("shareOutstanding")
    rev_per_share = metrics.get("revenuePerShareTTM")
    revenue = rev_per_share * shares_millions * 1_000_000 if (rev_per_share and shares_millions) else None
    margin = metrics.get("netProfitMarginTTM")

    return {
        "longName": profile.get("name") or ticker,
        "currentPrice": quote.get("c"),
        "previousClose": quote.get("pc"),
        "trailingPE": metrics.get("peBasicExclExtraTTM"),
        "forwardPE": None,  # not available on Finnhub's free tier
        "beta": metrics.get("beta"),
        "marketCap": profile["marketCapitalization"] * 1_000_000 if profile.get("marketCapitalization") else None,
        "totalRevenue": revenue,
        "profitMargins": (margin / 100) if margin is not None else None,  # yfinance uses a 0-1 fraction
        "trailingEps": metrics.get("epsTTM"),
        "fiftyTwoWeekHigh": metrics.get("52WeekHigh"),
        "fiftyTwoWeekLow": metrics.get("52WeekLow"),
        "recommendationKey": None,  # analyst ratings aren't on Finnhub's free tier
        "targetMeanPrice": None,    # ditto for price targets
        # Finnhub reports this as a percentage already (e.g. 0.35 = 0.35%);
        # yfinance's dividendYield is a fraction (e.g. 0.0035 = 0.35%). The
        # due_diligence_report formatting multiplies by 100 either way, so
        # convert here to match yfinance's convention at the source.
        "dividendYield": (metrics["dividendYieldIndicatedAnnual"] / 100) if metrics.get("dividendYieldIndicatedAnnual") is not None else None,
    }


def _finnhub_quote(ticker: str) -> str | None:
    """Fallback market-data report via Finnhub's free tier, used only when
    yfinance (both .info and fast_info) fails — e.g. Yahoo IP rate limiting.
    Pulls price (quote), market cap (profile2), and P/E, EPS, margin, beta,
    52-week range (stock/metric) — same fields get_market_data's normal path
    returns, just from a different source. Returns None if no
    FINNHUB_API_KEY is configured or the price call fails, so callers can
    fall through to a clean error instead of a partial/misleading report."""
    if not FINNHUB_API_KEY:
        print(f"finnhub_skipped_no_key ticker={ticker}")
        return None

    data = _finnhub_get(_FINNHUB_QUOTE_URL, ticker)
    if not data:
        return None

    price = data.get("c")  # current price
    prev = data.get("pc")  # previous close
    if not price:
        print(f"finnhub_no_price ticker={ticker} data={data}")
        return None
    print(f"finnhub_success ticker={ticker} price={price}")

    change = "N/A"
    if prev:
        delta = price - prev
        pct = (delta / prev) * 100 if prev else 0
        sign = "+" if delta >= 0 else ""
        change = f"{sign}{delta:.2f} ({sign}{pct:.2f}%)"

    # Company profile (market cap, name, shares outstanding) and basic
    # financials (P/E, margin, beta, ...) are separate free Finnhub
    # endpoints — best-effort, since losing them shouldn't lose the price.
    profile = _finnhub_get(_FINNHUB_PROFILE_URL, ticker) or {}
    metrics = (_finnhub_get(_FINNHUB_METRIC_URL, ticker, {"metric": "all"}) or {}).get("metric", {})

    company = profile.get("name") or ticker
    shares_millions = profile.get("shareOutstanding")  # Finnhub reports this in millions of shares
    market_cap = profile["marketCapitalization"] * 1_000_000 if profile.get("marketCapitalization") else None

    revenue = None
    rev_per_share = metrics.get("revenuePerShareTTM")
    if rev_per_share and shares_millions:
        revenue = rev_per_share * shares_millions * 1_000_000

    margin = metrics.get("netProfitMarginTTM")  # already a percentage, e.g. 27.15

    return f"""
Market Data — {company} ({ticker}) — via Finnhub fallback (Yahoo rate-limited)
═══════════════════════════════════════════════════════
Price:          {_fmt_price(price)}   Change: {change}
52W High:       {_fmt_price(metrics.get('52WeekHigh'))}
52W Low:        {_fmt_price(metrics.get('52WeekLow'))}

Fundamentals:
  Market Cap:   {_fmt_cap(market_cap)}
  Trailing P/E: {_fmt_ratio(metrics.get('peBasicExclExtraTTM'))}
  EPS (TTM):    {_fmt_ratio(metrics.get('epsTTM'))}
  Revenue:      {_fmt_cap(revenue)}
  Margin:       {_fmt_ratio(margin, 1) + '%' if margin is not None else 'N/A'}
  Beta:         {_fmt_ratio(metrics.get('beta'))}
═══════════════════════════════════════════════════════
""".strip()

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


def _price_fallback(t, ticker: str) -> str | None:
    """Try fast_info, then Finnhub, for at least a price when the full .info
    call didn't yield one. Returns None if both fail, so the caller can
    decide what to do (return a clean error rather than fabricate data)."""
    try:
        fi = t.fast_info
        price = fi.get("lastPrice")
        prev = fi.get("previousClose")
        if price is not None:
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
    except Exception as fi_exc:
        print(f"fast_info_fallback_failed ticker={ticker} error={fi_exc}")

    return _finnhub_quote(ticker)


def _get_market_data_one(ticker: str) -> str:
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
        fallback = _price_fallback(t, ticker)
        if fallback:
            return fallback
        return f"Error fetching data for {ticker}: {exc}"

    # A Yahoo rate limit doesn't always surface as an exception here — yfinance
    # can swallow the 429 internally and return `info` "successfully" with the
    # price fields simply missing. Check for that explicitly rather than only
    # trusting the try/except, or this silently returns a report with no price
    # and no error, which the model then can't distinguish from "no data".
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    if price is None:
        fallback = _price_fallback(t, ticker)
        if fallback:
            return fallback
        return f"Error fetching data for {ticker}: Yahoo returned no price (likely rate-limited)."

    # News is a nice-to-have — a Yahoo rate limit on this call alone
    # shouldn't discard the price/fundamentals we already fetched above.
    try:
        news = yf_with_retry(lambda: t.news) or []
    except Exception:
        news = []

    company = info.get("longName") or info.get("shortName") or ticker
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
def get_market_data(tickers: str) -> str:
    """Fetch live stock price, fundamentals, and recent news for one or more ticker symbols.

    Args:
        tickers: One ticker, or multiple comma-separated tickers to cover every
            company in the request in a single call (e.g. 'AAPL' or
            'AAPL,MSFT,GOOGL'). Always pass every ticker needed at once —
            never call this tool separately for each ticker in a comparison.
    """
    symbols = [s.strip().upper() for s in tickers.split(",") if s.strip()]
    if not symbols:
        return "No ticker provided."
    return "\n\n".join(_get_market_data_one(sym) for sym in symbols)


@tool
def get_fx_rate(currency_pair: str) -> str:
    """Fetch exchange rates: either vs UAH from NBU, or cross-currency pairs from Yahoo Finance.

    Args:
        currency_pair: Either a single currency code (e.g. 'USD', 'EUR') for rate vs UAH,
                      or a pair like 'USD/EUR', 'EUR/USD' for cross-currency rates
    """
    pair = currency_pair.strip().upper()

    # Check if it's a cross-currency pair (USD/EUR, EUR/USD, etc.)
    if "/" in pair:
        parts = pair.split("/")
        if len(parts) != 2:
            return f"Invalid currency pair format: '{pair}'. Use format like 'USD/EUR' or single code like 'USD'."

        base, quote = parts[0].strip(), parts[1].strip()

        # If quote is UAH, use NBU
        if quote == "UAH":
            return _fetch_nbu_rate(base)

        # Otherwise use Yahoo Finance FX pair
        # Yahoo format: base+quote+"=X" (e.g. EURUSD=X for EUR/USD)
        yahoo_symbol = f"{base}{quote}=X"
        try:
            ticker = yf.Ticker(yahoo_symbol)
            info = yf_with_retry(lambda: ticker.info) or {}
            price = info.get("regularMarketPrice") or info.get("bid")

            if price is None:
                # Try fast_info as fallback
                try:
                    price = ticker.fast_info.get("lastPrice")
                except Exception:
                    pass

            if price is None:
                return f"No exchange rate data available for {base}/{quote}. Check currency codes are valid."

            prev = info.get("regularMarketPreviousClose")
            change = ""
            if prev:
                delta = price - prev
                pct = (delta / prev) * 100
                sign = "+" if delta >= 0 else ""
                change = f"  Change: {sign}{delta:.4f} ({sign}{pct:.2f}%)"

            return f"Exchange rate — {base}/{quote}: {price:.4f}{change}"

        except Exception as exc:
            return f"Error fetching FX rate for {base}/{quote}: {exc}"

    # Single currency code - get rate vs UAH from NBU
    return _fetch_nbu_rate(pair)


_THRESHOLDS = {
    "conservative": {"max_pe": 25, "max_beta": 1.0, "max_position": "5%"},
    "moderate":     {"max_pe": 35, "max_beta": 1.4, "max_position": "10%"},
    "aggressive":   {"max_pe": 60, "max_beta": 2.0, "max_position": "20%"},
}


def _due_diligence_one(ticker: str, risk_profile: str) -> str:
    ticker = ticker.strip().upper()
    profile = risk_profile.lower()
    thresholds = _THRESHOLDS.get(profile, _THRESHOLDS["moderate"])

    source_note = ""
    try:
        t = yf.Ticker(ticker)
        info = yf_with_retry(lambda: t.info) or {}
        if not (info.get("currentPrice") or info.get("regularMarketPrice")):
            # Same silent-rate-limit shape seen in get_market_data: .info can
            # "succeed" with an empty/near-empty dict instead of raising.
            raise ValueError("Yahoo returned no price (likely rate-limited)")
    except Exception as exc:
        info = _finnhub_info_dict(ticker)
        if info is None:
            return f"Error fetching data for {ticker}: {exc}"
        source_note = " — via Finnhub fallback (Yahoo rate-limited)"

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
  Company:       {company} ({ticker}){source_note}
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
def due_diligence_report(tickers: str, risk_profile: str) -> str:
    """Generate an institutional Due Diligence report with APPROVED or REJECTED verdict.

    Args:
        tickers: One ticker, or multiple comma-separated tickers to screen in
            a single call (e.g. 'NVDA' or 'NVDA,AAPL'). Always pass every
            ticker needed at once — never call this tool separately per ticker.
        risk_profile: One of 'conservative', 'moderate', or 'aggressive'
    """
    symbols = [s.strip().upper() for s in tickers.split(",") if s.strip()]
    if not symbols:
        return "No ticker provided."
    return "\n\n".join(_due_diligence_one(sym, risk_profile) for sym in symbols)


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


@tool
def web_search(query: str) -> str:
    """Search the web for current information, news, or data not available in other tools.

    Use this for:
    - Cryptocurrency prices and data (Bitcoin, Ethereum, etc.)
    - Commodity prices (gold, oil, silver, wheat, etc.)
    - Recent financial news and events
    - Economic indicators (inflation, GDP, unemployment rates)
    - Information about private companies (not publicly traded)
    - General financial questions requiring current web data

    Args:
        query: Search query in natural language (e.g. 'Bitcoin price today', 'current oil price WTI')
    """
    tavily_key = os.getenv("TAVILY_API_KEY", "")

    # Try Tavily first (if API key is set)
    if tavily_key:
        try:
            resp = httpx.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": tavily_key,
                    "query": query,
                    "search_depth": "basic",
                    "max_results": 3,
                },
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()

            results = data.get("results", [])
            if not results:
                return f"No web results found for: {query}"

            output = f"Web search results for '{query}':\n\n"
            for i, result in enumerate(results[:3], 1):
                title = result.get("title", "")
                content = result.get("content", "")
                url = result.get("url", "")
                output += f"{i}. {title}\n"
                if content:
                    # Limit content to ~200 chars per result
                    output += f"   {content[:200]}{'...' if len(content) > 200 else ''}\n"
                if url:
                    output += f"   Source: {url}\n"
                output += "\n"

            return output.strip()

        except Exception as exc:
            print(f"tavily_search_failed query={query} error={exc}")
            # Fall through to DuckDuckGo

    # Fallback to DuckDuckGo (free, no API key needed)
    try:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))

        if not results:
            return f"No web results found for: {query}"

        output = f"Web search results for '{query}':\n\n"
        for i, result in enumerate(results, 1):
            title = result.get("title", "")
            body = result.get("body", "")
            href = result.get("href", "")
            output += f"{i}. {title}\n"
            if body:
                output += f"   {body[:200]}{'...' if len(body) > 200 else ''}\n"
            if href:
                output += f"   Source: {href}\n"
            output += "\n"

        return output.strip()

    except ImportError:
        return (
            "Web search unavailable: neither TAVILY_API_KEY is set nor "
            "duckduckgo-search library is installed. Install with: "
            "pip install duckduckgo-search"
        )
    except Exception as exc:
        return f"Web search failed for '{query}': {exc}"


TOOLS = [
    get_market_data,
    due_diligence_report,
    kelly_position_size,
    fetch_sec_10k_tool,
    compare_annual_reports,
    get_earnings_calendar,
    screen_stocks,
    get_fx_rate,
    web_search,
]
