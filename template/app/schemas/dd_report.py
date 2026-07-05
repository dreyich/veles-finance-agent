"""Structured Due Diligence Report schema.

The agent produces this via structured output (response_format=DDReport).
Used by the /analyze endpoint — returns clean JSON instead of raw text.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Verdict(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ValuationSection(BaseModel):
    trailing_pe: Optional[float] = Field(None, description="Trailing P/E ratio")
    forward_pe: Optional[float] = Field(None, description="Forward P/E ratio")
    sector_avg_pe: Optional[float] = Field(None, description="Sector average P/E")
    assessment: str = Field(..., description="2-3 sentence valuation commentary")
    is_expensive: bool = Field(..., description="True if trading above sector average")


class FinancialHealthSection(BaseModel):
    market_cap_b: Optional[float] = Field(None, description="Market cap in billions USD")
    dividend_yield_pct: Optional[float] = Field(None, description="Dividend yield %")
    assessment: str = Field(..., description="2-3 sentence financial health commentary")


class NewsSentimentSection(BaseModel):
    sentiment: str = Field(..., description="bullish | bearish | neutral")
    headlines: list[str] = Field(default_factory=list, description="Key headlines used")
    assessment: str = Field(..., description="1-2 sentence news summary")


class DDReport(BaseModel):
    """Institutional Due Diligence Report — structured output from the agent.

    This schema enforces that the agent always returns a complete,
    machine-parseable report rather than free-form text.
    """

    ticker: str = Field(..., description="Stock ticker symbol")
    company_name: str = Field(..., description="Full company name")
    risk_profile: str = Field(..., description="conservative | moderate | aggressive")
    analysis_date: str = Field(..., description="ISO 8601 date of analysis")

    valuation: ValuationSection
    financial_health: FinancialHealthSection
    news_sentiment: NewsSentimentSection

    verdict: Verdict = Field(..., description="APPROVED or REJECTED")
    justification: str = Field(
        ...,
        min_length=20,
        description="One-sentence justification for the verdict tied to risk profile",
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0,
        description="Agent's confidence in the verdict (0.0–1.0)",
    )
    thinking_summary: Optional[str] = Field(
        None,
        description="Condensed internal reasoning (from <thinking> block)",
    )


class AnalyzeRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=10, description="Stock ticker (e.g. NVDA)")
    risk_profile: str = Field(
        "moderate",
        pattern="^(conservative|moderate|aggressive)$",
        description="User risk tolerance",
    )
