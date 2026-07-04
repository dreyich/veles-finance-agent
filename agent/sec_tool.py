"""
SEC EDGAR tool — завантажує останній 10-K та передає ключові секції
моделі Veles-Finance-7B-v5 для структурованої екстракції даних.

Стратегія:
  1. XBRL CompanyFacts API → структурований JSON з числовими даними (без парсингу HTML)
  2. Submissions API → метадані filing (дата, accession)
  3. Veles модель → якісний аналіз (ризики, прогноз) з MD&A тексту
"""
from __future__ import annotations
import os
import re
import json
import httpx
from openai import OpenAI
from langchain_core.tools import tool

_VELES_BASE = os.getenv("VELES_BASE_URL", "http://localhost:11434/v1")
_VELES_MODEL = os.getenv("VELES_MODEL", "veles")
client = OpenAI(base_url=_VELES_BASE, api_key=os.getenv("VELES_API_KEY", "ollama"))

HEADERS = {"User-Agent": "Veles Finance Agent contact@veles.ai"}
BASE = "https://data.sec.gov"


# ── Step 1: CIK lookup ────────────────────────────────────────────────────────

def _get_cik(ticker: str) -> str | None:
    """Map ticker → CIK using SEC's company_tickers.json."""
    try:
        r = httpx.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers=HEADERS, timeout=15
        )
        data = r.json()
        ticker_upper = ticker.upper().replace("-", "")
        for entry in data.values():
            if entry["ticker"].upper() == ticker_upper:
                return str(entry["cik_str"]).zfill(10)
    except Exception:
        return None
    return None


# ── Step 2: Latest 10-K filing metadata ──────────────────────────────────────

def _get_latest_10k(cik: str) -> dict | None:
    """Return accession number and filing date of the most recent 10-K."""
    try:
        r = httpx.get(
            f"{BASE}/submissions/CIK{cik}.json",
            headers=HEADERS, timeout=15
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


# ── Step 3: XBRL CompanyFacts API ────────────────────────────────────────────

# XBRL concept name → our field name
_XBRL_MAP = {
    "Revenues":                                  "total_revenue",
    "RevenueFromContractWithCustomerExcludingAssessedTax": "total_revenue",
    "RevenueFromContractWithCustomerIncludingAssessedTax": "total_revenue",
    "SalesRevenueNet":                           "total_revenue",
    "NetIncomeLoss":                             "net_income",
    "Assets":                                    "total_assets",
    "LongTermDebt":                              "total_debt",
    "LongTermDebtAndCapitalLeaseObligations":    "total_debt",
    "DebtCurrent":                               "debt_current",
    "CashAndCashEquivalentsAtCarryingValue":     "cash_and_equivalents",
    "CashCashEquivalentsAndShortTermInvestments":"cash_and_equivalents",
    "NetCashProvidedByUsedInOperatingActivities":"operating_cash_flow",
    "GrossProfit":                               "gross_profit",
    "CostOfRevenue":                             "cost_of_revenue",
    "CostOfGoodsSold":                           "cost_of_revenue",
    "CostOfGoodsAndServicesSold":                "cost_of_revenue",
    "EarningsPerShareDiluted":                   "eps_diluted",
    "CommonStockSharesOutstanding":              "shares_outstanding",
    "StockholdersEquity":                        "stockholders_equity",
}


def _get_xbrl_facts(cik: str) -> dict:
    """Fetch structured financial data via XBRL CompanyFacts API.

    All metrics are aligned to the same fiscal year end date to avoid
    mixing numbers from different periods.

    Returns a dict with financial metrics in millions USD (or millions shares).
    """
    try:
        r = httpx.get(
            f"{BASE}/api/xbrl/companyfacts/CIK{cik}.json",
            headers=HEADERS, timeout=30
        )
        facts = r.json()
    except Exception:
        return {}

    us_gaap = facts.get("facts", {}).get("us-gaap", {})

    # ── Phase 1: find the canonical fiscal year end date ──────────────────────
    # Take the LATEST end date across all revenue concepts (companies change GAAP concepts)
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
        annual = [
            e for e in entries
            if e.get("form") == "10-K" and e.get("end") and e.get("val") is not None
        ]
        if annual:
            annual.sort(key=lambda e: e["end"], reverse=True)
            candidate = annual[0]["end"]
            if target_end is None or candidate > target_end:
                target_end = candidate

    def _value_for_period(concept_data: dict, unit_key: str, target: str | None) -> float | None:
        """Pick the 10-K value that best represents a full fiscal year near target_end.

        Prefers entries with ~12-month duration (start→end ≈ 300-400 days).
        Point-in-time concepts (balance sheet) have no start date and are always used.
        """
        from datetime import date as _date
        entries = concept_data.get("units", {}).get(unit_key, [])
        annual = [
            e for e in entries
            if e.get("form") == "10-K" and e.get("end") and e.get("val") is not None
        ]
        if not annual:
            return None

        annual.sort(key=lambda e: e["end"], reverse=True)

        t_date = _date.fromisoformat(target) if target else None

        def _is_full_year(e: dict) -> bool:
            """True if period covers ~12 months (or is a point-in-time snapshot)."""
            start = e.get("start")
            if not start:
                return True  # balance sheet: point-in-time, no start
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

        # Priority 1: full-year entry with matching period end
        for e in annual:
            if _is_full_year(e) and e.get("end") == target:
                return e["val"] / 1_000_000

        # Priority 2: full-year entry within ±365 days of target
        for e in annual:
            if _is_full_year(e) and _date_ok(e):
                return e["val"] / 1_000_000

        # Priority 3: any entry within ±365 days
        for e in annual:
            if _date_ok(e):
                return e["val"] / 1_000_000

        # No match within target period → return None so next concept is tried
        return None

    # ── Phase 2: extract each metric ─────────────────────────────────────────
    result: dict = {}
    for xbrl_name, field in _XBRL_MAP.items():
        if xbrl_name not in us_gaap or field in result:
            continue
        concept = us_gaap[xbrl_name]
        units = concept.get("units", {})
        # EPS uses "USD/shares"; balance-sheet items use "USD"; counts use "shares"
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
        # EPS and per-share values must NOT be divided by 1M — fix scaling
        if unit_key == "USD/shares":
            # _value_for_period divides by 1M, undo that for EPS
            entry_vals = [
                e["val"] for e in concept["units"][unit_key]
                if e.get("form") == "10-K" and e.get("end") == target_end and e.get("val") is not None
            ]
            if entry_vals:
                val = entry_vals[0]  # raw EPS value (not in millions)
            else:
                val = val * 1_000_000  # undo the /1M from _value_for_period
        result[field] = round(val, 4) if unit_key == "USD/shares" else round(val, 2)

    # ── Phase 3: derived metrics ──────────────────────────────────────────────
    # Derive gross_profit from cost_of_revenue if direct tag unavailable
    if "gross_profit" not in result and "cost_of_revenue" in result and "total_revenue" in result:
        result["gross_profit"] = round(result["total_revenue"] - result.pop("cost_of_revenue"), 2)
    else:
        result.pop("cost_of_revenue", None)  # drop if gross_profit already present

    if "gross_profit" in result and "total_revenue" in result and result["total_revenue"]:
        result["gross_margin_pct"] = round(result["gross_profit"] / result["total_revenue"] * 100, 1)
    if "net_income" in result and "total_revenue" in result and result["total_revenue"]:
        result["net_margin_pct"] = round(result["net_income"] / result["total_revenue"] * 100, 1)

    # Combine current + long-term debt
    if "debt_current" in result and "total_debt" in result:
        result["total_debt"] = round(result["total_debt"] + result.pop("debt_current"), 2)
    elif "debt_current" in result:
        result["total_debt"] = result.pop("debt_current")

    result["fiscal_year_end"] = target_end
    return result


# ── Step 4: Qualitative analysis via Veles model ──────────────────────────────

def _fmt_accession(acc_no_dashes: str) -> str:
    """Convert '000032019325000079' → '0000320193-25-000079'."""
    a = acc_no_dashes.zfill(18)
    return f"{a[:10]}-{a[10:12]}-{a[12:]}"


def _get_qualitative_text(cik: str, accession: str, max_chars: int = 5000) -> str:
    """Download 10-K text and extract MD&A + Risk Factors for qualitative analysis."""
    cik_int = int(cik)
    acc_fmt = _fmt_accession(accession)

    # Try full submission text file (most reliable)
    try:
        r = httpx.get(
            f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession}/{acc_fmt}.txt",
            headers=HEADERS, timeout=45
        )
        if r.status_code == 200 and len(r.text) > 1000:
            text = _clean_html(r.text)
            # Find Item 1A (Risk Factors) — usually has most qualitative content
            section = _extract_best_section(text, ["1A", "7"], max_chars)
            if len(section) > 200:
                return section
    except Exception:
        pass
    return ""


def _clean_html(html: str) -> str:
    """Strip HTML/SGML tags and normalize whitespace."""
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&#\d+;', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _extract_best_section(text: str, section_names: list[str], max_chars: int) -> str:
    """Find a substantial section from a list of Item names, skipping ToC entries.

    ToC heuristic: if within 200 chars after the match there's a short page-number
    pattern (e.g. '12', '32') or a quick jump to the next Item, it's a ToC entry.
    Real sections have long narrative paragraphs — detected by a high density of
    sentence-ending punctuation in the 500 chars following the match.
    """
    for name in section_names:
        pattern = rf'(?i)item\s*{re.escape(name)}[A-Z]?[\.\s]'
        matches = list(re.finditer(pattern, text))
        for m in matches:
            after = text[m.start(): m.start() + 600]
            # ToC entries: within first 100 chars there's a standalone number (page ref)
            first_100 = after[:100]
            if re.search(r'\b\d{1,3}\s*(?:Item|\Z)', first_100):
                continue  # likely ToC — skip

            # Real sections have narrative content: periods, commas, long words
            period_count = after.count('.') + after.count(',')
            word_count = len(after.split())
            if period_count >= 5 and word_count >= 60:
                return text[m.start(): m.start() + max_chars]

    return ""


QUALITATIVE_PROMPT = """You are Veles, a financial analyst specialized in SEC 10-K analysis.

Based on this 10-K filing excerpt, extract:
1. Three main risk factors (each max 15 words)
2. Management outlook in one sentence

Return ONLY valid JSON:
{{"key_risks": ["risk1", "risk2", "risk3"], "management_outlook": "one sentence"}}

10-K excerpt:
{text}

JSON:"""


_IS_SGLANG = "11434" not in _VELES_BASE  # True when using SGLang/vLLM, not Ollama

# JSON schema for XGrammar-enforced structured output (SGLang only)
_QUALITATIVE_SCHEMA = {
    "type": "object",
    "properties": {
        "key_risks": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 3,
        },
        "management_outlook": {"type": "string"},
    },
    "required": ["key_risks", "management_outlook"],
}


def _extract_qualitative(text: str) -> dict:
    """Use Veles model to extract risks and outlook from 10-K text.

    On SGLang (production): uses XGrammar JSON schema enforcement for 100%
    structural validity with no regex fallback needed.
    On Ollama (development): falls back to regex JSON extraction.
    """
    if not text or len(text) < 100:
        return {"key_risks": [], "management_outlook": None}

    snippet = text[:1200]
    prompt = QUALITATIVE_PROMPT.format(text=snippet)
    try:
        if _IS_SGLANG:
            # XGrammar: hardware-guaranteed JSON output, no post-processing needed
            resp = client.chat.completions.create(
                model=_VELES_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0,
                response_format={"type": "json_schema", "json_schema": {"name": "qualitative_analysis", "schema": _QUALITATIVE_SCHEMA}},
            )
            return json.loads(resp.choices[0].message.content or "{}")
        else:
            # Ollama: no grammar enforcement, use regex fallback
            resp = client.chat.completions.create(
                model=_VELES_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0,
                extra_body={"options": {"num_ctx": 2048}},
            )
            content = resp.choices[0].message.content or ""
            m = re.search(r'\{.*\}', content, re.DOTALL)
            if m:
                return json.loads(m.group())
    except Exception:
        pass
    return {"key_risks": [], "management_outlook": None}


# ── Main tool function ────────────────────────────────────────────────────────

def fetch_sec_10k(ticker: str) -> dict:
    """
    Fetch the latest 10-K from SEC EDGAR and extract key financial data.

    Uses:
      - XBRL CompanyFacts API for structured numeric data (no HTML parsing needed)
      - Veles model for qualitative analysis (risks, outlook) from MD&A text

    Args:
        ticker: Stock ticker (e.g. 'AAPL', 'NVDA')

    Returns:
        Dict with filing metadata + extracted financials
    """
    ticker = ticker.strip().upper()
    result = {"ticker": ticker, "source": "SEC EDGAR 10-K"}

    # Step 1: CIK lookup
    cik = _get_cik(ticker)
    if not cik:
        return {"ticker": ticker, "error": f"CIK not found for {ticker}"}
    result["cik"] = cik

    # Step 2: Filing metadata
    filing = _get_latest_10k(cik)
    if not filing:
        return {"ticker": ticker, "error": "No 10-K filing found"}
    result["filing_date"] = filing["date"]
    result["accession"] = filing["accession_fmt"]
    result["company_name"] = filing.get("company_name", ticker)
    result["edgar_url"] = (
        f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=10-K"
    )

    # Step 3: XBRL structured data (fast, reliable, no HTML)
    xbrl_data = _get_xbrl_facts(cik)
    financials: dict = dict(xbrl_data)

    # Step 4: Qualitative analysis via Veles (risks, outlook)
    qual_text = _get_qualitative_text(cik, filing["accession"])
    if qual_text:
        qual = _extract_qualitative(qual_text)
        financials["key_risks"] = qual.get("key_risks", [])
        financials["management_outlook"] = qual.get("management_outlook")
    else:
        financials["key_risks"] = []
        financials["management_outlook"] = None

    result["financials"] = financials
    return result


@tool
def fetch_sec_10k_tool(ticker: str) -> str:
    """Fetch the latest SEC 10-K annual report for a company and extract key financial data.

    Use this when the user asks about annual reports, SEC filings, 10-K documents,
    or wants deeper fundamental analysis beyond what Yahoo Finance provides.

    Args:
        ticker: Stock ticker symbol (e.g. 'AAPL', 'NVDA', 'MSFT')
    """
    data = fetch_sec_10k(ticker)
    return format_sec_report(data)


def format_sec_report(data: dict) -> str:
    """Format SEC extraction result as readable text."""
    if "error" in data and "financials" not in data:
        return f"SEC EDGAR Error for {data.get('ticker', '?')}: {data['error']}"

    ticker = data.get("ticker", "?")
    date = data.get("filing_date", "N/A")
    url = data.get("edgar_url", "")
    fin = data.get("financials", {})

    if "error" in fin:
        return f"10-K fetched ({date}) but extraction failed: {fin['error']}"

    def fmt_m(v):
        if v is None: return "N/A"
        if abs(v) >= 1000: return f"${v/1000:.2f}B"
        return f"${v:.1f}M"

    risks = fin.get("key_risks", [])
    risks_str = "\n".join(f"  • {r}" for r in risks[:3]) if risks else "  N/A"

    return f"""
SEC 10-K Report — {ticker}
Filing date: {date} | Source: {url}
══════════════════════════════════════════════════
Financial Highlights (from annual report):
  Revenue:          {fmt_m(fin.get('total_revenue'))}
  Net Income:       {fmt_m(fin.get('net_income'))}
  Total Assets:     {fmt_m(fin.get('total_assets'))}
  Total Debt:       {fmt_m(fin.get('total_debt'))}
  Cash:             {fmt_m(fin.get('cash_and_equivalents'))}
  Operating CF:     {fmt_m(fin.get('operating_cash_flow'))}
  Gross Margin:     {f"{fin.get('gross_margin_pct'):.1f}%" if fin.get('gross_margin_pct') else "N/A"}
  Net Margin:       {f"{fin.get('net_margin_pct'):.1f}%" if fin.get('net_margin_pct') else "N/A"}
  EPS (diluted):    {f"${fin.get('eps_diluted'):.2f}" if fin.get('eps_diluted') else "N/A"}
  Fiscal Year End:  {fin.get('fiscal_year_end', 'N/A')}

Key Risks:
{risks_str}

Management Outlook:
  {fin.get('management_outlook', 'N/A')}
══════════════════════════════════════════════════
""".strip()
