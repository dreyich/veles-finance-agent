"""Due Diligence report generation tool.

Produces a consistently structured, institutional-grade DD report with a
deterministic APPROVED / REJECTED verdict. The verdict is enforced at the
schema level — the LLM cannot hedge or omit it.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

import structlog
from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator

logger = structlog.get_logger(__name__)


class Verdict(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RiskProfile(str, Enum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class DDReportInput(BaseModel):
    """Input schema for generate_dd_report."""

    ticker: str = Field(
        ...,
        description="Stock ticker symbol in uppercase (e.g. 'NVDA', 'AAPL').",
        min_length=1,
        max_length=10,
    )
    company_name: str = Field(
        ...,
        description="Full company name (e.g. 'NVIDIA Corporation').",
        min_length=1,
        max_length=120,
    )
    risk_profile: RiskProfile = Field(
        ...,
        description="Investor risk profile: 'conservative', 'moderate', or 'aggressive'.",
    )
    verdict: Verdict = Field(
        ...,
        description="Final suitability verdict — MUST be exactly 'APPROVED' or 'REJECTED'. No hedging allowed.",
    )
    verdict_rationale: str = Field(
        ...,
        description="One clear sentence explaining the primary reason for the verdict.",
        min_length=10,
        max_length=300,
    )
    key_strengths: list[str] = Field(
        ...,
        description="List of 2–5 concrete strengths (use actual numbers from market data).",
        min_length=2,
        max_length=5,
    )
    key_risks: list[str] = Field(
        ...,
        description="List of 2–5 concrete risks (use actual numbers and specific factors).",
        min_length=2,
        max_length=5,
    )
    price: str = Field(
        ...,
        description="Current stock price as a formatted string (e.g. '$875.40').",
    )
    market_cap: str = Field(
        ...,
        description="Market capitalisation as a formatted string (e.g. '$2.15T').",
    )
    pe_ratio: str = Field(
        ...,
        description="Trailing P/E ratio as a string (e.g. '45.2' or 'N/A').",
    )
    forward_pe: str = Field(
        ...,
        description="Forward P/E ratio as a string (e.g. '38.1' or 'N/A').",
    )
    eps: str = Field(
        ...,
        description="Earnings per share (TTM) as a string (e.g. '$19.44' or 'N/A').",
    )
    revenue: str = Field(
        ...,
        description="Annual revenue (TTM) as a formatted string (e.g. '$60.92B').",
    )
    profit_margin: str = Field(
        ...,
        description="Net profit margin as a string (e.g. '55.0%' or 'N/A').",
    )
    beta: str = Field(
        ...,
        description="Beta coefficient as a string (e.g. '1.64' or 'N/A').",
    )
    week_52_high: str = Field(
        ...,
        description="52-week high price as a formatted string.",
    )
    week_52_low: str = Field(
        ...,
        description="52-week low price as a formatted string.",
    )
    analyst_recommendation: str = Field(
        ...,
        description="Analyst consensus recommendation (e.g. 'BUY', 'HOLD', 'SELL').",
    )
    analyst_target: str = Field(
        ...,
        description="Mean analyst price target as a formatted string.",
    )
    position_size_pct: Optional[str] = Field(
        default=None,
        description="Recommended position size as a percentage string (e.g. '5.2%'). Leave None if not calculated.",
    )
    additional_notes: Optional[str] = Field(
        default=None,
        description="Any additional analyst notes, macro context, or qualitative observations. Max 500 chars.",
        max_length=500,
    )

    @field_validator("ticker")
    @classmethod
    def normalise_ticker(cls, v: str) -> str:
        return v.strip().upper()


_VERDICT_STYLES = {
    Verdict.APPROVED: ("✓", "APPROVED", "══════════════════════════════════════"),
    Verdict.REJECTED: ("✗", "REJECTED", "══════════════════════════════════════"),
}

_RISK_LABELS = {
    RiskProfile.CONSERVATIVE: "Conservative",
    RiskProfile.MODERATE: "Moderate",
    RiskProfile.AGGRESSIVE: "Aggressive",
}


@tool("generate_dd_report", args_schema=DDReportInput)
def generate_dd_report(
    ticker: str,
    company_name: str,
    risk_profile: str,
    verdict: str,
    verdict_rationale: str,
    key_strengths: list[str],
    key_risks: list[str],
    price: str,
    market_cap: str,
    pe_ratio: str,
    forward_pe: str,
    eps: str,
    revenue: str,
    profit_margin: str,
    beta: str,
    week_52_high: str,
    week_52_low: str,
    analyst_recommendation: str,
    analyst_target: str,
    position_size_pct: Optional[str] = None,
    additional_notes: Optional[str] = None,
) -> str:
    """Generate a structured institutional Due Diligence report with a mandatory APPROVED/REJECTED verdict.

    Use this tool as the FINAL step in every DD analysis, after calling get_market_data
    and completing your <thinking> analysis. It enforces consistent, institutional-grade
    report structure and prevents hedged or ambiguous verdicts.

    When to call this tool:
    - User asks to "analyse", "review", "DD", or "evaluate" any stock or asset
    - User asks for a suitability assessment against their risk profile
    - After gathering all market data via get_market_data

    Workflow:
    1. Call get_market_data(ticker) to get live data
    2. Reason through the analysis in <thinking> tags
    3. Call generate_dd_report(...) with your findings to produce the final report

    Args:
        ticker: Stock ticker in uppercase.
        company_name: Full company name.
        risk_profile: Investor profile — 'conservative', 'moderate', or 'aggressive'.
        verdict: MUST be 'APPROVED' or 'REJECTED'. No other values accepted.
        verdict_rationale: Primary reason for the verdict in one sentence.
        key_strengths: 2–5 concrete strengths with actual figures.
        key_risks: 2–5 concrete risks with actual figures.
        price: Current price (e.g. '$875.40').
        market_cap: Market cap (e.g. '$2.15T').
        pe_ratio: Trailing P/E (e.g. '45.2').
        forward_pe: Forward P/E (e.g. '38.1').
        eps: EPS TTM (e.g. '$19.44').
        revenue: Revenue TTM (e.g. '$60.92B').
        profit_margin: Net margin (e.g. '55.0%').
        beta: Beta coefficient (e.g. '1.64').
        week_52_high: 52-week high price.
        week_52_low: 52-week low price.
        analyst_recommendation: Consensus rating (e.g. 'BUY').
        analyst_target: Mean analyst price target.
        position_size_pct: Kelly-derived position size. Optional.
        additional_notes: Extra context, macro observations. Optional.

    Returns:
        A fully formatted institutional DD report as a string.
    """
    validated = DDReportInput(
        ticker=ticker,
        company_name=company_name,
        risk_profile=risk_profile,
        verdict=verdict,
        verdict_rationale=verdict_rationale,
        key_strengths=key_strengths,
        key_risks=key_risks,
        price=price,
        market_cap=market_cap,
        pe_ratio=pe_ratio,
        forward_pe=forward_pe,
        eps=eps,
        revenue=revenue,
        profit_margin=profit_margin,
        beta=beta,
        week_52_high=week_52_high,
        week_52_low=week_52_low,
        analyst_recommendation=analyst_recommendation,
        analyst_target=analyst_target,
        position_size_pct=position_size_pct,
        additional_notes=additional_notes,
    )

    symbol, label, bar = _VERDICT_STYLES[validated.verdict]
    profile_label = _RISK_LABELS[validated.risk_profile]
    generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    strengths_block = "\n".join(f"  + {s}" for s in validated.key_strengths)
    risks_block = "\n".join(f"  - {r}" for r in validated.key_risks)

    position_line = (
        f"  Recommended Size:  {validated.position_size_pct} of portfolio\n"
        if validated.position_size_pct
        else ""
    )

    notes_section = (
        f"\n── Analyst Notes ──────────────────────────────────────\n"
        f"  {validated.additional_notes}\n"
        if validated.additional_notes
        else ""
    )

    logger.info(
        "dd_report_generated",
        ticker=validated.ticker,
        verdict=validated.verdict.value,
        risk_profile=validated.risk_profile.value,
    )

    return f"""
╔══════════════════════════════════════════════════════╗
║         INSTITUTIONAL DUE DILIGENCE REPORT           ║
╚══════════════════════════════════════════════════════╝

  Company:       {validated.company_name} ({validated.ticker})
  Risk Profile:  {profile_label}
  Generated:     {generated_at}

── Market Snapshot ────────────────────────────────────
  Price:             {validated.price}
  Market Cap:        {validated.market_cap}
  52-Week High:      {validated.week_52_high}
  52-Week Low:       {validated.week_52_low}

── Fundamentals ───────────────────────────────────────
  Trailing P/E:      {validated.pe_ratio}
  Forward P/E:       {validated.forward_pe}
  EPS (TTM):         {validated.eps}
  Revenue (TTM):     {validated.revenue}
  Profit Margin:     {validated.profit_margin}
  Beta:              {validated.beta}

── Analyst Consensus ──────────────────────────────────
  Recommendation:    {validated.analyst_recommendation}
  Price Target:      {validated.analyst_target}

── Strengths ──────────────────────────────────────────
{strengths_block}

── Risks ──────────────────────────────────────────────
{risks_block}
{notes_section}
── Position Sizing ────────────────────────────────────
{position_line}  Profile Ceiling:   {"5% max" if validated.risk_profile == RiskProfile.CONSERVATIVE else "10% max" if validated.risk_profile == RiskProfile.MODERATE else "20% max"}

{bar}
  VERDICT:  {label} {symbol}

  {validated.verdict_rationale}
{bar}

Source: Yahoo Finance via yfinance · Veles Finance AI
""".strip()
