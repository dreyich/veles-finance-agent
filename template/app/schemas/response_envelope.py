"""Universal Envelope schema for structured Veles responses.

Every model response is wrapped in this envelope inside the <output> block.
Frontend uses `intent` to decide rendering: plain text vs financial widget.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class FinancialData(BaseModel):
    """Structured financial data extracted from the model's analysis."""

    # FX / currency fields
    currency_pair: Optional[str] = Field(None, examples=["USD/UAH", "EUR/USD"])
    rate: Optional[float] = Field(None, examples=[44.87])
    source: Optional[str] = Field(None, examples=["NBU", "Yahoo Finance", "FRED"])
    change_pct: Optional[float] = Field(None, description="% change vs previous close")

    # Equity fields
    ticker: Optional[str] = Field(None, examples=["AAPL", "NVDA"])
    price: Optional[float] = Field(None, examples=[196.40])
    market_cap: Optional[str] = Field(None, examples=["$2.94T"])

    # Analysis verdict
    verdict: Optional[Literal["APPROVED", "REJECTED"]] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="0.0–1.0")

    # Generic key-value pairs for macro data
    indicators: Optional[dict] = Field(None, description="Macro indicators as key-value pairs")


class VelesEnvelope(BaseModel):
    """Universal response envelope — always output inside <output> tags as JSON."""

    intent: Literal["chat", "fx_rate", "equity", "macro", "calculation"] = Field(
        ...,
        description=(
            "chat=general conversation | fx_rate=currency result | "
            "equity=stock analysis | macro=macro data | calculation=math result"
        ),
    )
    text_response: str = Field(
        ...,
        description="Full answer for the user in their language. Never empty.",
    )
    financial_data: Optional[FinancialData] = Field(
        None,
        description="Structured numbers for widget rendering. null when intent==chat.",
    )
