"""QuantOracle financial math tools for the Finance AI Agent.

Provides deterministic financial calculations to prevent LLM hallucinations
on quantitative questions.
"""

import httpx
from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator

QUANTORACLE_BASE_URL = "https://api.quantoracle.dev/v1"
TIMEOUT_SECONDS = 5.0


class KellyInput(BaseModel):
    """Input schema for the Kelly Criterion calculator."""

    win_probability: float = Field(
        ...,
        description="Probability of a winning trade, between 0 and 1 (e.g. 0.6 for 60%).",
        ge=0.01,
        le=0.99,
    )
    payout_ratio: float = Field(
        ...,
        description="Ratio of profit on a win to loss on a loss (e.g. 2.0 means you win $2 for every $1 risked).",
        gt=0.0,
    )

    @field_validator("win_probability")
    @classmethod
    def validate_edge(cls, p: float, info) -> float:
        # Warn if the strategy has negative expected value
        if hasattr(info, "data") and "payout_ratio" in info.data:
            b = info.data["payout_ratio"]
            edge = p * b - (1 - p)
            if edge <= 0:
                raise ValueError(
                    f"Strategy has no positive edge (expected value = {edge:.4f}). "
                    "Kelly Criterion requires a positive expected value to recommend any position."
                )
        return p


def _kelly_local(win_probability: float, payout_ratio: float) -> dict:
    """Pure-math Kelly Criterion calculation (no external dependency)."""
    p = win_probability
    q = 1.0 - p
    b = payout_ratio

    kelly_fraction = (p * b - q) / b
    half_kelly = kelly_fraction / 2.0
    expected_value = p * b - q

    return {
        "kelly_fraction": round(kelly_fraction, 6),
        "half_kelly_fraction": round(half_kelly, 6),
        "expected_value_per_unit": round(expected_value, 6),
        "win_probability": p,
        "payout_ratio": b,
        "source": "local_calculation",
    }


@tool("kelly_criterion_calculator", args_schema=KellyInput)
def kelly_criterion_calculator(win_probability: float, payout_ratio: float) -> str:
    """Calculate the optimal position size using the Kelly Criterion.

    Use this tool whenever a user asks about:
    - Optimal bet/position sizing for a trading strategy
    - Kelly Criterion or Kelly formula
    - How much capital to allocate given a win rate and payout ratio
    - Risk management for a strategy with a known edge

    The Kelly Criterion gives the mathematically optimal fraction of capital
    to risk on each trade to maximise long-run growth while avoiding ruin.

    Args:
        win_probability: Probability of a winning trade (0.01 – 0.99).
                         Example: 0.60 for a 60% win rate.
        payout_ratio:    Average profit / average loss ratio (must be > 0).
                         Example: 2.0 means winning trades return 2× the risk.

    Returns:
        A formatted string with the full Kelly analysis including recommended
        position sizes and practical guidance.
    """
    # Validate inputs via Pydantic before doing any work
    validated = KellyInput(win_probability=win_probability, payout_ratio=payout_ratio)
    p = validated.win_probability
    b = validated.payout_ratio

    # 1. Try the QuantOracle API (no key required, 1000 free calls/day)
    result = None
    try:
        response = httpx.post(
            f"{QUANTORACLE_BASE_URL}/risk/kelly",
            json={"win_probability": p, "payout_ratio": b},
            timeout=TIMEOUT_SECONDS,
        )
        if response.status_code == 200:
            result = response.json()
            result["source"] = "quantoracle_api"
    except Exception:
        # API unavailable — fall back to deterministic local calculation
        pass

    # 2. Fallback: calculate locally (identical math, zero latency)
    if result is None:
        result = _kelly_local(p, b)

    # 3. Format the response for the LLM and end-user
    kelly_pct = result["kelly_fraction"] * 100
    half_kelly_pct = result["half_kelly_fraction"] * 100
    ev = result["expected_value_per_unit"]
    source = result.get("source", "local_calculation")

    # Practical risk guidance
    if kelly_pct > 25:
        risk_note = (
            "⚠️  Full Kelly exceeds 25% — this is highly aggressive. "
            "Most professional traders use Half-Kelly or less to reduce volatility."
        )
    elif kelly_pct > 10:
        risk_note = (
            "The full Kelly allocation is moderate. Consider Half-Kelly "
            "for a better risk/reward balance in live trading."
        )
    else:
        risk_note = "Full Kelly is conservative here; it can be applied directly."

    return f"""
Kelly Criterion Analysis
═══════════════════════════════════════
Input Parameters:
  • Win Probability:  {p:.1%}
  • Payout Ratio:     {b:.2f}x  (win ${b:.2f} per $1 risked)
  • Expected Value:   +{ev:.4f} per unit risked

Optimal Position Sizing:
  • Full Kelly:       {kelly_pct:.2f}% of capital per trade
  • Half Kelly:       {half_kelly_pct:.2f}% of capital per trade  ← recommended for live trading
  • Quarter Kelly:    {kelly_pct / 4:.2f}% of capital per trade  ← ultra-conservative

Practical Guidance:
  {risk_note}

Example ($10,000 account):
  • Full Kelly  → risk ${10_000 * result['kelly_fraction']:,.2f} per trade
  • Half Kelly  → risk ${10_000 * result['half_kelly_fraction']:,.2f} per trade

Source: {source}
═══════════════════════════════════════
""".strip()
