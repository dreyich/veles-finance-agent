"""UniversalEnvelope — the single structured output contract for all agent responses.

Every LLM response MUST conform to this schema. This replaces free-form text output
and eliminates hallucinated formatting. The envelope is enforced via constrained
decoding (vLLM guided decoding / XGrammar) in Phase 1.2.

Intent taxonomy:
  chat        — general conversation, greeting, clarification (no financial_data)
  fx_rate     — any currency / exchange rate result
  equity      — stock or equity analysis
  macro       — macroeconomic data or indicator
  calculation — deterministic math result (IRP, DCF, Kelly, etc.)
  forecast    — forward-looking scenario analysis
  error       — agent could not complete the request

FinancialData is intentionally permissive (all fields Optional) so a single schema
covers FX, equity, and macro use-cases without requiring discriminated unions.
The frontend renders only the fields that are present.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class IntentEnum(str, Enum):
    CHAT = "chat"
    FX_RATE = "fx_rate"
    EQUITY = "equity"
    MACRO = "macro"
    CALCULATION = "calculation"
    FORECAST = "forecast"
    ERROR = "error"


class FinancialData(BaseModel):
    """Structured payload for financial results.

    All fields are Optional — populate only what applies to the intent.
    The frontend skips None fields when rendering widgets.
    """

    model_config = {"extra": "ignore"}

    # ── FX / Macro ────────────────────────────────────────────────
    currency_pair: Optional[str] = Field(None, examples=["USD/UAH", "EUR/USD"])
    rate: Optional[float] = Field(None, description="Spot or forecast rate")
    rate_forecast: Optional[float] = Field(None, description="IRP / model fair-value")
    rate_bull: Optional[float] = Field(None, description="Optimistic scenario")
    rate_bear: Optional[float] = Field(None, description="Pessimistic scenario")
    change_pct: Optional[float] = Field(None, description="% change vs prior close")
    source: Optional[str] = Field(None, examples=["NBU", "ECB", "FRED"])
    horizon_months: Optional[int] = Field(None, description="Forecast horizon in months")

    # ── Equity ────────────────────────────────────────────────────
    ticker: Optional[str] = Field(None, examples=["AAPL", "NVDA"])
    price: Optional[float] = Field(None, description="Current or target price USD")
    market_cap: Optional[str] = Field(None, examples=["$2.94T"])
    pe_ratio: Optional[float] = Field(None, description="Trailing P/E")
    eps: Optional[float] = Field(None, description="Earnings per share USD")

    # ── Shared verdict ────────────────────────────────────────────
    verdict: Optional[str] = Field(None, examples=["APPROVED", "REJECTED", "NEUTRAL"])
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)

    # ── Calculation metadata ──────────────────────────────────────
    model_used: Optional[str] = Field(None, examples=["IRP", "DCF", "Kelly", "PPP"])
    inputs: Optional[dict] = Field(None, description="Key inputs used in the calculation")


class UniversalEnvelope(BaseModel):
    """The single output contract for every agent response.

    The LLM is constrained to always produce this JSON via guided decoding.
    Downstream consumers (API, frontend, audit logger) work exclusively with
    this type — never with raw strings.

    Invariants:
      - intent is always set
      - text_response is always a non-empty string
      - financial_data is None when intent == "chat" or "error"
      - financial_data is populated for all numeric/financial intents
    """

    intent: IntentEnum = Field(
        ...,
        description="Semantic classification of the response",
    )
    expert_justification: str = Field(
        default="",
        description=(
            "Step-by-step expert reasoning: economic drivers, cause-effect relationships, "
            "model selection rationale, key assumptions, and risk factors. "
            "Written BEFORE the final answer to enforce structured chain-of-thought. "
            "Always in the same language as the user query."
        ),
    )
    text_response: str = Field(
        ...,
        min_length=1,
        description="Human-readable response in the user's language",
    )
    financial_data: Optional[FinancialData] = Field(
        None,
        description="Structured financial payload; None for chat/error intents",
    )
    thinking_summary: Optional[str] = Field(
        None,
        description="Condensed reasoning chain (from <thinking> block); max 500 chars",
        max_length=500,
    )
