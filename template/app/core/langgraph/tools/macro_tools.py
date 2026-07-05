"""Live macroeconomic data tools — US-first, worldwide coverage.

Sources (all free, no API key required for core data):
  - FRED (Federal Reserve) — US rates, CPI, GDP, unemployment
  - World Bank API       — global GDP, inflation, current account
  - ECB API              — EUR rates
  - NBU API              — UAH rate, reserves (Ukraine)
  - Open Exchange Rates  — FX spot rates (free tier)
  - Treasury.gov         — US yield curve

Temperature MUST be 0 for financial tasks — set DEFAULT_LLM_TEMPERATURE=0.0
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import structlog
from langchain_core.tools import tool
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

_TIMEOUT = 8.0
_cache: dict = {}
_CACHE_TTL = 60  # seconds


def _cached(key: str, fn):
    """Simple TTL cache to avoid redundant API calls within 60s."""
    import time
    now = time.time()
    if key in _cache and now - _cache[key]["ts"] < _CACHE_TTL:
        return _cache[key]["val"]
    val = fn()
    _cache[key] = {"val": val, "ts": now}
    return val
_FRED_BASE = "https://api.stlouisfed.org/fred"
_WORLD_BANK = "https://api.worldbank.org/v2"
_ECB_BASE = "https://data-api.ecb.europa.eu/service/data"
_NBU_BASE = "https://bank.gov.ua/NBU_Exchange"
_TREASURY = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"


# ── FRED series IDs ─────────────────────────────────────────────────────────
_FRED_SERIES = {
    "fed_funds_rate":    "FEDFUNDS",       # Federal Funds Rate
    "us_cpi_yoy":        "CPIAUCSL",       # US CPI (YoY)
    "us_cpi_core":       "CPILFESL",       # US Core CPI
    "us_unemployment":   "UNRATE",          # Unemployment rate
    "us_gdp_growth":     "A191RL1Q225SBEA", # Real GDP growth QoQ annualized
    "us_10y_yield":      "DGS10",           # 10-Year Treasury
    "us_2y_yield":       "DGS2",            # 2-Year Treasury
    "us_30y_yield":      "DGS30",           # 30-Year Treasury
    "us_real_gdp":       "GDPC1",           # Real GDP (billions)
    "us_m2":             "M2SL",            # M2 Money Supply
    "us_pce":            "PCE",             # Personal Consumption Expenditures
    "dollar_index":      "DTWEXBGS",        # USD Trade Weighted Index
    "us_ppi":            "PPIACO",          # Producer Price Index
    "vix":               "VIXCLS",          # VIX Volatility Index
    "us_retail_sales":   "RSXFS",           # Retail Sales ex food services
    "us_ip_index":       "INDPRO",          # Industrial Production Index
    "credit_spread_hy":  "BAMLH0A0HYM2",   # High Yield OAS
    "credit_spread_ig":  "BAMLC0A0CM",      # Investment Grade OAS
}

_COUNTRY_CODES = {
    "us": "US", "usa": "US", "united states": "US",
    "eu": "XC", "euro area": "XC", "eurozone": "XC",
    "uk": "GB", "britain": "GB",
    "china": "CN", "japan": "JP", "germany": "DE",
    "ukraine": "UA", "canada": "CA", "australia": "AU",
    "india": "IN", "brazil": "BR", "mexico": "MX",
    "south korea": "KR", "korea": "KR",
}


def _fred_latest(series_id: str) -> Optional[float]:
    """Fetch latest observation from FRED (no API key needed for public series)."""
    try:
        r = httpx.get(
            f"{_FRED_BASE}/series/observations",
            params={
                "series_id": series_id,
                "sort_order": "desc",
                "limit": 1,
                "file_type": "json",
                "api_key": "NONE",   # FRED works without key for public data
            },
            timeout=_TIMEOUT,
        )
        # Try without API key first
        if r.status_code != 200:
            r = httpx.get(
                f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}",
                timeout=_TIMEOUT,
            )
            lines = r.text.strip().split("\n")
            if len(lines) >= 2:
                val = lines[-1].split(",")[1].strip()
                return float(val) if val != "." else None
            return None

        obs = r.json().get("observations", [])
        if obs:
            val = obs[0].get("value", ".")
            return float(val) if val != "." else None
    except Exception as exc:
        logger.warning("fred_fetch_failed", series=series_id, error=str(exc))
    return None


def _fred_csv_latest(series_id: str) -> Optional[tuple[str, float]]:
    """Fetch latest value via FRED CSV endpoint (no auth needed)."""
    try:
        r = httpx.get(
            f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}",
            timeout=_TIMEOUT,
        )
        lines = [l for l in r.text.strip().split("\n") if l and not l.startswith("DATE")]
        if lines:
            last = lines[-1].split(",")
            if len(last) == 2 and last[1].strip() != ".":
                return last[0].strip(), float(last[1].strip())
    except Exception as exc:
        logger.warning("fred_csv_failed", series=series_id, error=str(exc))
    return None


def _worldbank_latest(country: str, indicator: str) -> Optional[tuple[float, int]]:
    """Fetch latest World Bank indicator for a country. Returns (value, year)."""
    try:
        r = httpx.get(
            f"{_WORLD_BANK}/country/{country}/indicator/{indicator}",
            params={"format": "json", "mrv": 2, "per_page": 2},
            timeout=_TIMEOUT,
        )
        data = r.json()
        if isinstance(data, list) and len(data) > 1:
            records = data[1] or []
            for rec in records:
                if rec.get("value") is not None:
                    year = int(rec.get("date", 0))
                    return float(rec["value"]), year
    except Exception as exc:
        logger.warning("worldbank_fetch_failed", country=country, indicator=indicator, error=str(exc))
    return None


def _nbu_rate() -> Optional[float]:
    """Fetch current NBU USD/UAH official rate (cached 60s)."""
    def _fetch():
        try:
            r = httpx.get(
                "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?valcode=USD&json",
                timeout=_TIMEOUT,
            )
            if r.status_code == 200:
                data = r.json()
                if data and isinstance(data, list):
                    return float(data[0].get("rate", 0)) or None
        except Exception as exc:
            logger.warning("nbu_fetch_failed", error=str(exc))
        return None
    return _cached("nbu_usd_uah", _fetch)

    # Fallback: exchangerate-api (free, no key, updated daily)
    try:
        r = httpx.get(
            "https://open.er-api.com/v6/latest/USD",
            timeout=_TIMEOUT,
        )
        if r.status_code == 200:
            rates = r.json().get("rates", {})
            if "UAH" in rates:
                return float(rates["UAH"])
    except Exception as exc:
        logger.warning("er_api_uah_fallback_failed", error=str(exc))

    return None


def _ecb_rate(key: str = "EUR.USD.SP00.A") -> Optional[float]:
    """Fetch ECB exchange rate or policy rate."""
    try:
        r = httpx.get(
            f"{_ECB_BASE}/EXR/{key}",
            params={"format": "csvdata", "lastNObservations": 1},
            timeout=_TIMEOUT,
        )
        lines = [l for l in r.text.strip().split("\n") if l and not l.startswith("KEY")]
        if lines:
            parts = lines[-1].split(",")
            if len(parts) > 7:
                return float(parts[7].strip())
    except Exception as exc:
        logger.warning("ecb_fetch_failed", key=key, error=str(exc))
    return None


# ── Tool schemas ─────────────────────────────────────────────────────────────

class MacroUSInput(BaseModel):
    indicators: list[str] = Field(
        default=["fed_funds_rate", "us_cpi_yoy", "us_10y_yield", "us_unemployment", "dollar_index"],
        description=(
            "List of indicators to fetch. Available: fed_funds_rate, us_cpi_yoy, us_cpi_core, "
            "us_unemployment, us_gdp_growth, us_10y_yield, us_2y_yield, us_30y_yield, "
            "us_m2, dollar_index, vix, credit_spread_hy, credit_spread_ig, "
            "us_retail_sales, us_ppi, us_ip_index"
        ),
    )

    from pydantic import field_validator

    @field_validator("indicators", mode="before")
    @classmethod
    def parse_json_string(cls, v):
        if isinstance(v, str):
            import json as _json
            try:
                parsed = _json.loads(v)
                return parsed if isinstance(parsed, list) else [v]
            except Exception:
                return [v]
        return v


class MacroGlobalInput(BaseModel):
    countries: list[str] = Field(
        ...,
        description="List of countries to fetch data for. E.g. ['US', 'EU', 'China', 'Ukraine'].",
    )
    indicators: list[str] = Field(
        default=["gdp_growth", "inflation", "unemployment"],
        description="Indicators: gdp_growth, inflation, unemployment, current_account, debt_to_gdp",
    )

    from pydantic import field_validator

    @field_validator("countries", "indicators", mode="before")
    @classmethod
    def parse_json_string(cls, v):
        if isinstance(v, str):
            import json as _json
            try:
                parsed = _json.loads(v)
                return parsed if isinstance(parsed, list) else [v]
            except Exception:
                return [v]
        return v


class FXRatesInput(BaseModel):
    base: str = Field(default="USD", description="Base currency (e.g. 'USD', 'EUR')")
    pairs: list[str] = Field(
        default=["EUR", "GBP", "JPY", "CNY", "UAH", "CHF", "AUD", "CAD"],
        description="List of target currency codes to get rates against base.",
    )

    from pydantic import field_validator

    @field_validator("pairs", mode="before")
    @classmethod
    def parse_json_string(cls, v):
        if isinstance(v, str):
            import json as _json
            try:
                parsed = _json.loads(v)
                return parsed if isinstance(parsed, list) else [v]
            except Exception:
                return [v]
        return v


class YieldCurveInput(BaseModel):
    country: str = Field(
        default="US",
        description="Country for yield curve. Currently supports: 'US', 'EU'.",
    )


# ── Tools ─────────────────────────────────────────────────────────────────────

@tool("get_us_macro_data", args_schema=MacroUSInput)
def get_us_macro_data(indicators: list[str]) -> str:
    """Fetch live US macroeconomic indicators from the Federal Reserve (FRED).

    Use this tool when analysing US economy, Fed policy, or any asset priced in USD.
    Always call this before making any USD-denominated forecast or rate analysis.

    Returns live data for: Fed Funds Rate, CPI (headline + core), unemployment,
    GDP growth, Treasury yields (2Y/10Y/30Y), M2 money supply, Dollar Index,
    VIX, credit spreads, retail sales, PPI, industrial production.

    Args:
        indicators: List of indicator keys to fetch. Use all defaults for a full snapshot.

    Returns:
        Formatted macro snapshot with values and dates.
    """
    results = {}
    for ind in indicators:
        series = _FRED_SERIES.get(ind)
        if not series:
            results[ind] = "unknown_indicator"
            continue
        val = _fred_csv_latest(series)
        results[ind] = val if val else ("N/A", None)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"US Macroeconomic Snapshot — {now}"]

    label_map = {
        "fed_funds_rate":   "Fed Funds Rate",
        "us_cpi_yoy":       "CPI (Headline, YoY %)",
        "us_cpi_core":      "Core CPI (ex food/energy, YoY %)",
        "us_unemployment":  "Unemployment Rate %",
        "us_gdp_growth":    "Real GDP Growth (QoQ ann. %)",
        "us_10y_yield":     "10-Year Treasury Yield %",
        "us_2y_yield":      "2-Year Treasury Yield %",
        "us_30y_yield":     "30-Year Treasury Yield %",
        "dollar_index":     "USD Trade-Weighted Index",
        "us_m2":            "M2 Money Supply ($B)",
        "vix":              "VIX (Fear Index)",
        "credit_spread_hy": "High Yield Credit Spread (bps)",
        "credit_spread_ig": "Inv. Grade Credit Spread (bps)",
        "us_retail_sales":  "Retail Sales ex-food ($M)",
        "us_ppi":           "Producer Price Index",
        "us_ip_index":      "Industrial Production Index",
    }

    for ind, val in results.items():
        label = label_map.get(ind, ind)
        if isinstance(val, tuple) and val[1] is not None:
            date_str, num = val
            lines.append(f"  {label:<40} {num:>10.2f}  [{date_str}]")
        else:
            lines.append(f"  {label:<40} {'N/A':>10}")

    # Yield curve analysis if we have both 2Y and 10Y
    r2 = results.get("us_2y_yield")
    r10 = results.get("us_10y_yield")
    if isinstance(r2, tuple) and isinstance(r10, tuple) and r2[1] and r10[1]:
        spread = r10[1] - r2[1]
        signal = "INVERTED (recession signal)" if spread < 0 else "NORMAL (positive slope)"
        lines.append("")
        lines.append(f"  Yield Curve (10Y-2Y spread):  {spread:+.2f}%  →  {signal}")

    lines.append("Source: Federal Reserve (FRED) — St. Louis Fed")
    return "\n".join(lines)


@tool("get_global_macro_data", args_schema=MacroGlobalInput)
def get_global_macro_data(countries: list[str], indicators: list[str]) -> str:
    """Fetch macroeconomic data for multiple countries from the World Bank.

    Use this tool for cross-country macro comparisons, EM analysis, or
    any question about global growth, inflation, or debt dynamics.

    Args:
        countries: Country names or codes. E.g. ['US', 'China', 'EU', 'Ukraine', 'India'].
        indicators: Macro indicators. Available: gdp_growth, inflation, unemployment,
                    current_account, debt_to_gdp, fx_reserves, trade_balance.

    Returns:
        Comparative macro table across requested countries.
    """
    _wb_indicators = {
        "gdp_growth":       ("NY.GDP.MKTP.KD.ZG", "GDP Growth %"),
        "inflation":        ("FP.CPI.TOTL.ZG",    "CPI Inflation %"),
        "unemployment":     ("SL.UEM.TOTL.ZS",     "Unemployment %"),
        "current_account":  ("BN.CAB.XOKA.GD.ZS",  "Current Account % GDP"),
        "debt_to_gdp":      ("GC.DOD.TOTL.GD.ZS",  "Gov Debt % GDP"),
        "fx_reserves":      ("FI.RES.TOTL.CD",      "FX Reserves (USD)"),
    }

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"Global Macro Comparison — {now}"]

    for country_input in countries:
        code = _COUNTRY_CODES.get(country_input.lower(), country_input.upper()[:2])
        lines.append(f"\n  {country_input.upper()} ({code}):")

        # Special case: Ukraine from NBU
        if code == "UA":
            uah = _nbu_rate()
            lines.append(f"    USD/UAH (NBU spot):  {uah:.2f}" if uah else "    USD/UAH:  N/A")

        for ind_key in indicators:
            if ind_key not in _wb_indicators:
                continue
            wb_code, label = _wb_indicators[ind_key]
            result = _worldbank_latest(code, wb_code)
            if result is not None:
                val, year = result
                val_str = f"{val:.2f}"
                lines.append(f"    {label:<35} {val_str:>8}  (data year: {year})")
            else:
                lines.append(f"    {label:<35}      N/A")

    lines.append("\nNOTE: World Bank data has 1-2 year publication lag. Year shown = actual data year, NOT current year.")
    lines.append("Source: World Bank Open Data API")
    return "\n".join(lines)


@tool("get_fx_rates", args_schema=FXRatesInput)
def get_fx_rates(base: str, pairs: list[str]) -> str:
    """Fetch live FX spot rates for a basket of currency pairs.

    Use this tool before any currency analysis, FX forecasting, or
    cross-border valuation. Returns live rates from ECB and NBU.

    Args:
        base: Base currency (usually 'USD' or 'EUR').
        pairs: Target currencies. E.g. ['EUR', 'GBP', 'JPY', 'UAH', 'CNY'].

    Returns:
        Current FX rates with percentage moves vs prior close where available.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"FX Rates ({base} base) — {now}"]

    fetched = {}

    # 1. yfinance — real market rates (most accurate, reflects actual trading)
    try:
        import yfinance as yf
        tickers_map = {pair: f"{base.upper()}{pair.upper()}=X" for pair in pairs}
        data = yf.download(
            list(tickers_map.values()),
            period="1d", interval="1m", progress=False, auto_adjust=True
        )
        if not data.empty:
            close = data["Close"] if "Close" in data.columns else data
            for pair, ticker in tickers_map.items():
                try:
                    val = float(close[ticker].dropna().iloc[-1]) if ticker in close.columns else None
                    if val:
                        fetched[pair.upper()] = val
                except Exception:
                    pass
    except Exception as exc:
        logger.warning("yfinance_fx_failed", error=str(exc))

    # 2. Open Exchange Rates for any missing pairs
    if len(fetched) < len(pairs):
        try:
            r = httpx.get(
                f"https://open.er-api.com/v6/latest/{base.upper()}",
                timeout=_TIMEOUT,
            )
            if r.status_code == 200:
                er_rates = r.json().get("rates", {})
                for pair in pairs:
                    if pair.upper() not in fetched and pair.upper() in er_rates:
                        fetched[pair.upper()] = er_rates[pair.upper()]
        except Exception as exc:
            logger.warning("fx_api_failed", error=str(exc))

    # 3. NBU for UAH — always override with official NBU rate (most accurate for Ukraine)
    nbu_uah: Optional[float] = None
    if "UAH" in pairs:
        nbu_uah = _nbu_rate()
        if nbu_uah:
            fetched["UAH"] = nbu_uah  # NBU beats any other source for UAH

    # Final fallback: NBU for UAH if still missing
    if "UAH" in pairs and "UAH" not in fetched:
        uah = _nbu_rate()
        if uah:
            fetched["UAH"] = uah

    for pair in pairs:
        rate = fetched.get(pair.upper())
        source = "NBU official" if pair.upper() == "UAH" else "market"
        if rate:
            lines.append(f"  {base.upper()}/{pair.upper():<6}  {rate:>12.4f}  [{source}]")
        else:
            lines.append(f"  {base.upper()}/{pair.upper():<6}  {'N/A':>12}")

    lines.append("Source: NBU (UAH) / yfinance / Open Exchange Rates")
    return "\n".join(lines)


@tool("get_yield_curve")
def get_yield_curve(country: str = "US") -> str:
    """Fetch the current yield curve (short to long end) for US or EU.

    Use this tool when analysing interest rate environment, duration risk,
    recession signals, or fixed income valuations.

    Args:
        country: 'US' (default) or 'EU'.

    Returns:
        Yield curve with spread analysis and recession signal.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"{country.upper()} Yield Curve — {now}"]

    if country.upper() == "US":
        tenors = {
            "3M":  "DGS3MO",
            "6M":  "DGS6MO",
            "1Y":  "DGS1",
            "2Y":  "DGS2",
            "3Y":  "DGS3",
            "5Y":  "DGS5",
            "7Y":  "DGS7",
            "10Y": "DGS10",
            "20Y": "DGS20",
            "30Y": "DGS30",
        }
        yields = {}
        for tenor, series in tenors.items():
            val = _fred_csv_latest(series)
            if val and val[1]:
                yields[tenor] = val[1]
                lines.append(f"  {tenor:<5}  {val[1]:>6.2f}%  [{val[0]}]")
            else:
                lines.append(f"  {tenor:<5}  {'N/A':>6}")

        # Key spreads
        lines.append("")
        if "10Y" in yields and "2Y" in yields:
            s = yields["10Y"] - yields["2Y"]
            sig = "⚠ INVERTED — recession signal" if s < 0 else "✓ Normal slope"
            lines.append(f"  10Y-2Y Spread:   {s:+.2f}%  →  {sig}")
        if "10Y" in yields and "3M" in yields:
            s = yields["10Y"] - yields["3M"]
            sig = "⚠ INVERTED" if s < 0 else "✓ Normal"
            lines.append(f"  10Y-3M Spread:   {s:+.2f}%  →  {sig}")

    lines.append("Source: US Treasury / FRED")
    return "\n".join(lines)
