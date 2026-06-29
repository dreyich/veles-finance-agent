"""
Veles Finance Miner Agent
Autonomously downloads and processes SEC 10-K filings for S&P 500 companies.
Runs locally on RTX 3060 (free). Builds a proprietary dataset for future fine-tuning.

Usage:
    python miner_agent.py                    # Mine all S&P 500
    python miner_agent.py --ticker AAPL      # Mine single ticker
    python miner_agent.py --limit 50         # Mine first 50 companies
    python miner_agent.py --status           # Show database stats
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("miner")

DB_PATH = Path(__file__).parent / "data" / "sec_10k.db"
EDGAR_BASE = "https://data.sec.gov"
HEADERS = {"User-Agent": "Veles Finance Agent lilbusinesspurp@gmail.com"}

# ── S&P 500 tickers (top 100 by market cap for initial run) ───────────────
SP500_TOP100 = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "BRK.B", "LLY", "AVGO",
    "TSLA", "WMT", "JPM", "V", "XOM", "UNH", "ORCL", "MA", "COST", "HD",
    "PG", "JNJ", "ABBV", "BAC", "KO", "NFLX", "CVX", "MRK", "TMUS", "AMD",
    "CRM", "PEP", "LIN", "ACN", "TMO", "CSCO", "MCD", "ABT", "GE", "IBM",
    "NOW", "ADBE", "DIS", "PM", "TXN", "GS", "CAT", "AXP", "ISRG", "INTU",
    "QCOM", "RTX", "SPGI", "UBER", "BKNG", "MS", "T", "NEE", "PFE", "SYK",
    "LOW", "AMGN", "BLK", "SCHW", "ETN", "VRTX", "DE", "BSX", "MDT", "MU",
    "AMAT", "ADI", "CB", "CI", "MMC", "ELV", "LRCX", "KLAC", "AMT", "DHR",
    "PANW", "ZTS", "ICE", "BMY", "SO", "DUK", "AON", "CME", "TJX", "APH",
    "WM", "INTC", "PLD", "HCA", "NOC", "USB", "MCK", "TGT", "ITW", "GD",
]


# ── Database ───────────────────────────────────────────────────────────────

def init_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS filings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker      TEXT NOT NULL,
            cik         TEXT NOT NULL,
            company     TEXT,
            fiscal_year INTEGER,
            period_end  TEXT,
            revenue     REAL,
            net_income  REAL,
            eps         REAL,
            total_assets REAL,
            total_debt  REAL,
            equity      REAL,
            op_cash_flow REAL,
            raw_facts   TEXT,
            mined_at    TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ticker ON filings(ticker)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_year ON filings(fiscal_year)")
    conn.commit()
    return conn


def already_mined(conn: sqlite3.Connection, ticker: str, year: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM filings WHERE ticker=? AND fiscal_year=?", (ticker, year)
    ).fetchone()
    return row is not None


# ── EDGAR API ──────────────────────────────────────────────────────────────

_TICKERS_CACHE: dict = {}

def get_cik(ticker: str, client: httpx.Client) -> str | None:
    global _TICKERS_CACHE
    if not _TICKERS_CACHE:
        try:
            r = client.get("https://www.sec.gov/files/company_tickers.json", headers=HEADERS)
            _TICKERS_CACHE = r.json()
        except Exception:
            pass

    ticker_upper = ticker.upper().replace(".", "-")
    for entry in _TICKERS_CACHE.values():
        if entry.get("ticker", "").upper() == ticker_upper:
            return str(entry["cik_str"]).zfill(10)
    return None


def get_company_facts(cik: str, client: httpx.Client) -> dict | None:
    try:
        r = client.get(
            f"{EDGAR_BASE}/api/xbrl/companyfacts/CIK{cik}.json",
            headers=HEADERS,
            timeout=30.0,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def extract_annual_values(facts: dict, concept: str, unit: str = "USD") -> list[dict]:
    """Extract annual 10-K values for a given XBRL concept."""
    try:
        us_gaap = facts.get("facts", {}).get("us-gaap", {})
        concept_data = us_gaap.get(concept, {})
        units = concept_data.get("units", {})
        # Try requested unit, then all available units
        candidates = units.get(unit, [])
        if not candidates:
            for vals in units.values():
                candidates = vals
                break
        annual = [
            v for v in candidates
            if v.get("form") == "10-K" and v.get("fp") == "FY"
        ]
        annual.sort(key=lambda x: x.get("end", ""), reverse=True)
        return annual
    except Exception:
        return []


def mine_ticker(ticker: str, conn: sqlite3.Connection, client: httpx.Client) -> bool:
    log.info(f"Mining {ticker}...")

    cik = get_cik(ticker, client)
    if not cik:
        log.warning(f"{ticker}: CIK not found")
        return False

    facts = get_company_facts(cik, client)
    if not facts:
        log.warning(f"{ticker}: facts not available")
        return False

    company_name = facts.get("entityName", ticker)

    # Key financial concepts (XBRL standard names)
    concepts = {
        "revenue":       ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
        "net_income":    ["NetIncomeLoss"],
        "eps":           ["EarningsPerShareDiluted", "EarningsPerShareBasic"],
        "total_assets":  ["Assets"],
        "total_debt":    ["LongTermDebt", "LongTermDebtNoncurrent"],
        "equity":        ["StockholdersEquity"],
        "op_cash_flow":  ["NetCashProvidedByUsedInOperatingActivities"],
    }

    def best_annual(names: list[str], unit: str = "USD") -> tuple[float | None, str | None, int | None]:
        """Pick most recent value across all candidate concept names."""
        best_end = ""
        best_val = None
        best_year = None
        for name in names:
            values = extract_annual_values(facts, name, unit)
            if values and values[0].get("end", "") > best_end:
                v = values[0]
                best_end = v.get("end", "")
                best_val = v.get("val")
                best_year = int(best_end[:4]) if best_end else None
        return best_val, best_end or None, best_year

    revenue, period_end, fiscal_year = best_annual(concepts["revenue"])
    net_income, _, _ = best_annual(concepts["net_income"])
    eps, _, _ = best_annual(concepts["eps"], unit="USD/shares")
    total_assets, _, _ = best_annual(concepts["total_assets"])
    total_debt, _, _ = best_annual(concepts["total_debt"])
    equity, _, _ = best_annual(concepts["equity"])
    op_cash_flow, _, _ = best_annual(concepts["op_cash_flow"])

    if fiscal_year and already_mined(conn, ticker, fiscal_year):
        log.info(f"{ticker} {fiscal_year}: already in DB")
        return True

    # Store minimal raw facts for future fine-tuning
    raw = {
        "cik": cik,
        "concepts": {k: extract_annual_values(facts, v[0])[:3] for k, v in concepts.items()},
    }

    conn.execute("""
        INSERT INTO filings
            (ticker, cik, company, fiscal_year, period_end,
             revenue, net_income, eps, total_assets, total_debt, equity, op_cash_flow, raw_facts)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        ticker.upper(), cik, company_name, fiscal_year, period_end,
        revenue, net_income, eps, total_assets, total_debt, equity, op_cash_flow,
        json.dumps(raw),
    ))
    conn.commit()

    log.info(
        f"{ticker} {fiscal_year}: rev=${revenue/1e9:.1f}B  ni=${net_income/1e9:.1f}B  eps=${eps}"
        if revenue else f"{ticker}: stored (partial data)"
    )
    return True


# ── Main ───────────────────────────────────────────────────────────────────

def print_stats(conn: sqlite3.Connection):
    total = conn.execute("SELECT COUNT(*) FROM filings").fetchone()[0]
    tickers = conn.execute("SELECT COUNT(DISTINCT ticker) FROM filings").fetchone()[0]
    latest = conn.execute("SELECT MAX(mined_at) FROM filings").fetchone()[0]
    print(f"\n{'='*50}")
    print(f"SEC 10-K Database Stats")
    print(f"{'='*50}")
    print(f"Total filings:  {total}")
    print(f"Unique tickers: {tickers}")
    print(f"Last mined:     {latest}")
    print(f"DB location:    {DB_PATH}")
    print(f"{'='*50}\n")

    top = conn.execute("""
        SELECT ticker, company, fiscal_year, revenue/1e9
        FROM filings WHERE revenue IS NOT NULL
        ORDER BY revenue DESC LIMIT 10
    """).fetchall()
    if top:
        print("Top 10 by Revenue (latest 10-K):")
        for t, c, y, r in top:
            print(f"  {t:8s} {y}  ${r:.0f}B  {c}")


def main():
    parser = argparse.ArgumentParser(description="Veles Finance Miner Agent")
    parser.add_argument("--ticker", help="Mine single ticker")
    parser.add_argument("--limit", type=int, help="Limit number of tickers")
    parser.add_argument("--status", action="store_true", help="Show DB stats")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between requests (sec)")
    args = parser.parse_args()

    conn = init_db()

    if args.status:
        print_stats(conn)
        return

    tickers = [args.ticker.upper()] if args.ticker else SP500_TOP100
    if args.limit:
        tickers = tickers[:args.limit]

    log.info(f"Starting miner: {len(tickers)} tickers, delay={args.delay}s")
    log.info(f"Database: {DB_PATH}")

    success = failed = skipped = 0
    with httpx.Client(timeout=30.0) as client:
        for i, ticker in enumerate(tickers, 1):
            log.info(f"[{i}/{len(tickers)}] {ticker}")
            try:
                ok = mine_ticker(ticker, conn, client)
                if ok:
                    success += 1
                else:
                    failed += 1
            except Exception as e:
                log.error(f"{ticker}: {e}")
                failed += 1
            time.sleep(args.delay)

    log.info(f"\nDone: {success} success, {failed} failed, {skipped} skipped")
    print_stats(conn)


if __name__ == "__main__":
    main()
