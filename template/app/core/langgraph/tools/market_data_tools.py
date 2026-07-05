"""Market data tools for the Finance AI Agent.

Provides real-time stock data via yfinance: price, fundamentals, and news headlines.
Uses deterministic formatting to prevent LLM hallucinations on financial figures.
"""

import structlog
import yfinance as yf
from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = structlog.get_logger(__name__)

_MARKET_CAP_LABELS = [
    (1_000_000_000_000, "T"),
    (1_000_000_000, "B"),
    (1_000_000, "M"),
]
_MAX_NEWS_ITEMS = 5


def _fmt_market_cap(value: float | None) -> str:
    if value is None:
        return "N/A"
    for threshold, suffix in _MARKET_CAP_LABELS:
        if abs(value) >= threshold:
            return f"${value / threshold:.2f}{suffix}"
    return f"${value:,.0f}"


def _fmt_price(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"${value:,.2f}"


def _fmt_ratio(value: float | None, decimals: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{decimals}f}"


class MarketDataInput(BaseModel):
    """Input schema for the market data tool."""

    ticker: str = Field(
        ...,
        description="Stock ticker symbol in uppercase (e.g. 'AAPL', 'NVDA', 'TSLA', 'MSFT').",
        min_length=1,
        max_length=10,
    )

    @field_validator("ticker")
    @classmethod
    def normalise_ticker(cls, v: str) -> str:
        cleaned = v.strip().upper()
        if not cleaned.replace(".", "").replace("-", "").isalnum():
            raise ValueError(f"Invalid ticker symbol: '{v}'")
        return cleaned


@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    reraise=True,
)
def _fetch_ticker_data(ticker: str) -> tuple[dict, list[dict]]:
    """Fetch info and news from yfinance with retry logic."""
    t = yf.Ticker(ticker)
    info = t.info or {}
    news: list[dict] = t.news or []
    return info, news


@tool("get_market_data", args_schema=MarketDataInput)
def get_market_data(ticker: str) -> str:
    """Fetch real-time stock price, key fundamentals, and recent news for any ticker.

    Use this tool whenever a user asks about:
    - Current stock price or market data for a specific company
    - Fundamental metrics: P/E ratio, market capitalisation, EPS, dividend yield
    - Recent news or headlines about a company
    - A quick overview or snapshot of a stock (e.g. "analyse NVDA", "what's Apple at?")
    - Comparing valuation metrics across companies

    The tool returns live data sourced from Yahoo Finance. Do NOT use it for
    portfolio calculations or position sizing — use kelly_criterion_calculator for that.

    Args:
        ticker: Stock ticker symbol in uppercase (e.g. 'AAPL', 'NVDA', 'TSLA').

    Returns:
        A formatted string with current price, fundamentals snapshot, and up to
        5 recent news headlines with source attribution.
    """
    validated = MarketDataInput(ticker=ticker)
    t = validated.ticker

    logger.info("market_data_fetch_started", ticker=t)

    try:
        info, news = _fetch_ticker_data(t)
    except Exception as exc:
        logger.exception("market_data_fetch_failed", ticker=t, error=str(exc))
        return (
            f"Market Data Error — {t}\n"
            "---------------------------------------\n"
            f"Could not retrieve data for '{t}'. "
            "Please verify the ticker symbol and try again. "
            f"Detail: {exc}"
        )

    # Guard: yfinance returns a minimal dict for unknown tickers
    company_name = info.get("longName") or info.get("shortName") or t
    if not info.get("regularMarketPrice") and not info.get("currentPrice"):
        logger.warning("market_data_empty_response", ticker=t)
        return (
            f"Market Data — {t}\n"
            "---------------------------------------\n"
            f"No data found for ticker '{t}'. "
            "The symbol may be delisted, misspelled, or not supported by Yahoo Finance."
        )

    # ── Price ──────────────────────────────────────────────────────────────────
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
    price_change: str = "N/A"
    price_change_pct: str = "N/A"
    if price is not None and prev_close:
        delta = price - prev_close
        pct = (delta / prev_close) * 100
        sign = "+" if delta >= 0 else ""
        price_change = f"{sign}{delta:.2f}"
        price_change_pct = f"{sign}{pct:.2f}%"

    # ── Fundamentals ───────────────────────────────────────────────────────────
    market_cap = _fmt_market_cap(info.get("marketCap"))
    pe_ratio = _fmt_ratio(info.get("trailingPE"))
    forward_pe = _fmt_ratio(info.get("forwardPE"))
    eps = _fmt_ratio(info.get("trailingEps"))
    revenue = _fmt_market_cap(info.get("totalRevenue"))
    gross_margin = _fmt_ratio(
        info.get("grossMargins") * 100 if info.get("grossMargins") is not None else None, 1
    )
    profit_margin = _fmt_ratio(
        info.get("profitMargins") * 100 if info.get("profitMargins") is not None else None, 1
    )
    dividend_yield = (
        _fmt_ratio(info.get("dividendYield") * 100, 2) + "%"
        if info.get("dividendYield")
        else "None"
    )
    week_52_high = _fmt_price(info.get("fiftyTwoWeekHigh"))
    week_52_low = _fmt_price(info.get("fiftyTwoWeekLow"))
    beta = _fmt_ratio(info.get("beta"))
    analyst_target = _fmt_price(info.get("targetMeanPrice"))
    recommendation = (info.get("recommendationKey") or "N/A").upper().replace("_", " ")
    currency = info.get("currency", "USD")
    exchange = info.get("exchange") or info.get("fullExchangeName") or "N/A"
    sector = info.get("sector") or "N/A"
    industry = info.get("industry") or "N/A"

    # ── News ───────────────────────────────────────────────────────────────────
    news_lines: list[str] = []
    for i, item in enumerate(news[:_MAX_NEWS_ITEMS], start=1):
        # yfinance 1.x news schema
        content = item.get("content") or {}
        title = (
            content.get("title")
            or item.get("title")
            or "(no title)"
        )
        provider = (
            content.get("provider", {}).get("displayName")
            or item.get("publisher")
            or "Unknown"
        )
        news_lines.append(f"  {i}. {title}  [{provider}]")

    news_section = "\n".join(news_lines) if news_lines else "  No recent news available."

    logger.info(
        "market_data_fetch_completed",
        ticker=t,
        price=price,
        news_count=len(news_lines),
    )

    return f"""
Market Data Snapshot — {company_name} ({t})
Exchange: {exchange}  |  Sector: {sector}  |  Industry: {industry}
Currency: {currency}

PRICE
  Current Price:     {_fmt_price(price)}
  Change vs Close:   {price_change} ({price_change_pct})
  52-Week High:      {week_52_high}
  52-Week Low:       {week_52_low}

FUNDAMENTALS
  Market Cap:        {market_cap}
  Revenue (TTM):     {revenue}
  Trailing P/E:      {pe_ratio}
  Forward P/E:       {forward_pe}
  EPS (TTM):         {eps}
  Gross Margin:      {gross_margin}%
  Profit Margin:     {profit_margin}%
  Dividend Yield:    {dividend_yield}
  Beta:              {beta}

ANALYST CONSENSUS
  Mean Price Target: {analyst_target}
  Recommendation:    {recommendation}

RECENT NEWS ({len(news_lines)} headlines)
{news_section}
Source: Yahoo Finance (via yfinance)
""".strip()
