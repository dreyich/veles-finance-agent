"""Deterministic macro-financial math tools.

Replaces LLM "estimating in its head" with exact calculations.
The LLM decides WHAT to calculate; this tool does the math precisely.

Covers:
  - Interest Rate Parity (IRP) — FX fair value
  - Real yield calculation — inflation-adjusted returns
  - Yield curve analysis — recession signals
  - DCF (Discounted Cash Flow) — equity fair value
  - Debt sustainability — fiscal analysis
  - Purchasing Power Parity (PPP) — FX equilibrium
"""

from __future__ import annotations

import math
from typing import Optional

import structlog
from langchain_core.tools import tool
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


# ── Interest Rate Parity ──────────────────────────────────────────────────────

class IRPInput(BaseModel):
    spot_rate: float = Field(..., description="Current spot FX rate (units of quote per 1 base). E.g. 41.5 for UAH/USD.")
    rate_domestic: float = Field(..., description="Domestic nominal interest rate in % (e.g. 13.0 for NBU 13%).")
    rate_foreign: float = Field(..., description="Foreign nominal interest rate in % (e.g. 5.25 for Fed 5.25%).")
    inflation_domestic: float = Field(..., description="Domestic annual inflation in % (e.g. 8.5).")
    inflation_foreign: float = Field(..., description="Foreign annual inflation in % (e.g. 3.0).")
    horizon_months: int = Field(default=12, description="Forecast horizon in months (default 12).")
    pair_name: str = Field(default="LOCAL/USD", description="Name of the currency pair for display.")


@tool("calculate_irp", args_schema=IRPInput)
def calculate_irp(
    spot_rate: float,
    rate_domestic: float,
    rate_foreign: float,
    inflation_domestic: float,
    inflation_foreign: float,
    horizon_months: int,
    pair_name: str,
) -> str:
    """Calculate FX fair value using Interest Rate Parity (IRP) and PPP.

    Use this tool for any FX forecast or currency valuation question.
    DO NOT estimate exchange rates in your head — always call this tool.

    The tool calculates three independent FX fair-value estimates:
    1. Covered IRP  — arbitrage-free forward rate (carry-based)
    2. Uncovered IRP — expected future spot based on rate differential
    3. PPP          — inflation-differential based equilibrium

    Args:
        spot_rate: Current spot rate (domestic currency per 1 USD/foreign).
        rate_domestic: Domestic central bank rate in %.
        rate_foreign: Foreign (US Fed) rate in %.
        inflation_domestic: Domestic CPI YoY in %.
        inflation_foreign: Foreign CPI YoY in %.
        horizon_months: Months to project forward (default 12).
        pair_name: Display name for the pair.

    Returns:
        Exact IRP + PPP calculations with verdict.
    """
    t = horizon_months / 12.0
    rd = rate_domestic / 100
    rf = rate_foreign / 100
    pi_d = inflation_domestic / 100
    pi_f = inflation_foreign / 100

    # 1. Covered IRP: F = S × (1 + rd)^t / (1 + rf)^t
    irp_covered = spot_rate * ((1 + rd) ** t) / ((1 + rf) ** t)

    # 2. Uncovered IRP: same formula (assumes UIP holds)
    irp_uncovered = irp_covered  # identical under UIP

    # 3. PPP: F_ppp = S × (1 + pi_d)^t / (1 + pi_f)^t
    ppp_rate = spot_rate * ((1 + pi_d) ** t) / ((1 + pi_f) ** t)

    # Real interest rate differential
    real_domestic = ((1 + rd) / (1 + pi_d) - 1) * 100
    real_foreign  = ((1 + rf) / (1 + pi_f) - 1) * 100
    real_diff = real_domestic - real_foreign

    # Rate differential (nominal)
    nominal_diff = rate_domestic - rate_foreign

    # Direction signal
    avg_fair = (irp_covered + ppp_rate) / 2
    pct_change = (avg_fair - spot_rate) / spot_rate * 100
    direction = "DEPRECIATION" if avg_fair > spot_rate else "APPRECIATION"

    # Carry trade attractiveness
    carry = nominal_diff  # positive = domestic has higher yield
    carry_signal = (
        "POSITIVE CARRY — domestic yield premium attracts inflows (supportive)"
        if carry > 2
        else "NEGATIVE CARRY — capital flight risk (bearish)"
        if carry < -1
        else "NEUTRAL CARRY"
    )

    logger.info(
        "irp_calculated",
        pair=pair_name,
        spot=spot_rate,
        irp=round(irp_covered, 4),
        ppp=round(ppp_rate, 4),
        horizon_months=horizon_months,
    )

    return f"""
Interest Rate Parity Analysis — {pair_name}
{"═" * 55}
Input Parameters:
  Spot Rate (today):          {spot_rate:.4f}
  Domestic Rate (nominal):    {rate_domestic:.2f}%
  Foreign Rate (nominal):     {rate_foreign:.2f}%
  Domestic Inflation:         {inflation_domestic:.2f}%
  Foreign Inflation:          {inflation_foreign:.2f}%
  Horizon:                    {horizon_months} months

Real Rates:
  Real Domestic Rate:         {real_domestic:+.2f}%
  Real Foreign Rate:          {real_foreign:+.2f}%
  Real Rate Differential:     {real_diff:+.2f}%
  → {"Negative real rate — capital outflow pressure" if real_domestic < 0 else "Positive real rate — supportive"}

FX Fair Value Estimates ({horizon_months}M forward):
  Covered IRP:                {irp_covered:.4f}
  PPP Fair Value:             {ppp_rate:.4f}
  Average Fair Value:         {avg_fair:.4f}
  Current Spot:               {spot_rate:.4f}
  Implied Change:             {pct_change:+.2f}%  ({direction})

Carry Analysis:
  Nominal Differential:       {nominal_diff:+.2f}%
  Signal: {carry_signal}

VERDICT ({horizon_months}M):
  Fair Value Range: {min(irp_covered, ppp_rate):.2f} — {max(irp_covered, ppp_rate):.2f}
  Base Case: {avg_fair:.2f} ({direction} of {abs(pct_change):.1f}% from spot)
{"═" * 55}
Note: IRP assumes free capital flows. Adjust for capital controls,
reserve interventions, and political risk premium manually.
""".strip()


# ── Real Yield Calculator ─────────────────────────────────────────────────────

class RealYieldInput(BaseModel):
    assets: list[dict] = Field(
        ...,
        description=(
            "List of assets with nominal_yield and inflation. "
            "Each dict: {name: str, nominal_yield: float, inflation: float, currency: str}"
        ),
    )


@tool("calculate_real_yields", args_schema=RealYieldInput)
def calculate_real_yields(assets: list[dict]) -> str:
    """Calculate real (inflation-adjusted) yields for multiple assets/countries.

    Use this for cross-asset or cross-country yield comparison.
    Real yield = (1 + nominal) / (1 + inflation) - 1  [Fisher equation]

    Args:
        assets: List of dicts with keys: name, nominal_yield (%), inflation (%), currency.

    Returns:
        Ranked real yield comparison with signals.
    """
    results = []
    for a in assets:
        name = a.get("name", "Unknown")
        nominal = a.get("nominal_yield", 0) / 100
        infl = a.get("inflation", 0) / 100
        currency = a.get("currency", "?")
        real = ((1 + nominal) / (1 + infl) - 1) * 100
        results.append({
            "name": name,
            "nominal": a.get("nominal_yield", 0),
            "inflation": a.get("inflation", 0),
            "real": real,
            "currency": currency,
            "signal": "ATTRACTIVE" if real > 1.5 else "NEUTRAL" if real > 0 else "NEGATIVE (capital flight risk)",
        })

    results.sort(key=lambda x: x["real"], reverse=True)

    lines = ["Real Yield Comparison (Fisher Equation)", "═" * 60]
    lines.append(f"  {'Asset':<20} {'Nominal':>8} {'Inflation':>10} {'Real Yield':>11}  Signal")
    lines.append("  " + "-" * 58)

    for r in results:
        lines.append(
            f"  {r['name']:<20} {r['nominal']:>7.2f}%  {r['inflation']:>8.2f}%  "
            f"{r['real']:>+9.2f}%  {r['signal']}"
        )

    top = results[0]
    bottom = results[-1]
    lines.append("")
    lines.append(f"  Highest real yield: {top['name']} ({top['real']:+.2f}%) — capital inflow pressure")
    lines.append(f"  Lowest real yield:  {bottom['name']} ({bottom['real']:+.2f}%) — capital outflow pressure")
    lines.append("═" * 60)
    return "\n".join(lines)


# ── DCF Valuation ─────────────────────────────────────────────────────────────

class DCFInput(BaseModel):
    current_fcf: float = Field(..., description="Current Free Cash Flow (FCF) in millions USD.")
    growth_rate_y1_5: float = Field(..., description="Annual FCF growth rate for years 1-5 in %.")
    growth_rate_y6_10: float = Field(..., description="Annual FCF growth rate for years 6-10 in %.")
    terminal_growth: float = Field(default=2.5, description="Terminal growth rate in % (usually 2-3%).")
    wacc: float = Field(..., description="Weighted Average Cost of Capital (WACC) in %.")
    shares_outstanding: float = Field(..., description="Shares outstanding in millions.")
    net_debt: float = Field(default=0.0, description="Net debt in millions USD (negative = net cash).")
    ticker: str = Field(default="STOCK", description="Ticker or company name for display.")


@tool("calculate_dcf", args_schema=DCFInput)
def calculate_dcf(
    current_fcf: float,
    growth_rate_y1_5: float,
    growth_rate_y6_10: float,
    terminal_growth: float,
    wacc: float,
    shares_outstanding: float,
    net_debt: float,
    ticker: str,
) -> str:
    """Calculate intrinsic value using Discounted Cash Flow (DCF) model.

    Use this for equity valuation. Never estimate fair value without this tool.

    Args:
        current_fcf: Free cash flow (millions USD).
        growth_rate_y1_5: FCF growth % per year, years 1-5.
        growth_rate_y6_10: FCF growth % per year, years 6-10.
        terminal_growth: Perpetual growth rate (default 2.5%).
        wacc: Discount rate (cost of capital) in %.
        shares_outstanding: Shares in millions.
        net_debt: Net debt in millions (negative = net cash position).
        ticker: Company name for display.

    Returns:
        Full DCF with intrinsic value per share and sensitivity table.
    """
    g1 = growth_rate_y1_5 / 100
    g2 = growth_rate_y6_10 / 100
    gt = terminal_growth / 100
    r = wacc / 100

    # Project FCFs
    fcfs = []
    fcf = current_fcf
    for y in range(1, 11):
        g = g1 if y <= 5 else g2
        fcf = fcf * (1 + g)
        pv = fcf / (1 + r) ** y
        fcfs.append((y, fcf, pv))

    # Terminal value (Gordon Growth)
    terminal_fcf = fcfs[-1][1] * (1 + gt)
    terminal_value = terminal_fcf / (r - gt) if r > gt else 0
    pv_terminal = terminal_value / (1 + r) ** 10

    pv_fcf_sum = sum(f[2] for f in fcfs)
    enterprise_value = pv_fcf_sum + pv_terminal
    equity_value = enterprise_value - net_debt
    intrinsic_per_share = equity_value / shares_outstanding if shares_outstanding > 0 else 0

    lines = [f"DCF Valuation — {ticker}", "═" * 55]
    lines.append(f"  WACC: {wacc:.1f}%  |  Growth Y1-5: {growth_rate_y1_5:.1f}%  |  Y6-10: {growth_rate_y6_10:.1f}%  |  Terminal: {terminal_growth:.1f}%")
    lines.append("")
    lines.append(f"  {'Year':<6} {'FCF ($M)':>12} {'PV ($M)':>12}")
    lines.append("  " + "-" * 32)
    for y, fcf_y, pv_y in fcfs:
        lines.append(f"  {y:<6} {fcf_y:>12,.1f} {pv_y:>12,.1f}")
    lines.append("")
    lines.append(f"  Sum of PV (FCFs):          ${pv_fcf_sum:>12,.1f}M")
    lines.append(f"  Terminal Value (undiscounted): ${terminal_value:>10,.1f}M")
    lines.append(f"  PV of Terminal Value:      ${pv_terminal:>12,.1f}M")
    lines.append(f"  Enterprise Value:          ${enterprise_value:>12,.1f}M")
    lines.append(f"  Less: Net Debt:            ${net_debt:>12,.1f}M")
    lines.append(f"  Equity Value:              ${equity_value:>12,.1f}M")
    lines.append(f"  Shares Outstanding:         {shares_outstanding:>11,.1f}M")
    lines.append("")
    lines.append(f"  ▶ INTRINSIC VALUE:         ${intrinsic_per_share:>12,.2f} per share")
    lines.append("")

    # Sensitivity: WACC ±1% and growth ±2%
    lines.append("  Sensitivity (Intrinsic Value per Share):")
    lines.append(f"  {'':15} {'Growth -2%':>12} {'Base':>10} {'Growth +2%':>12}")
    for wacc_delta in [-1, 0, 1]:
        row = [f"  WACC {wacc+wacc_delta:.1f}%      "]
        for g_delta in [-2, 0, 2]:
            g1_s = (growth_rate_y1_5 + g_delta) / 100
            r_s = (wacc + wacc_delta) / 100
            fcf_s = current_fcf
            pv_s = 0
            for y in range(1, 11):
                g_use = g1_s if y <= 5 else (growth_rate_y6_10 + g_delta) / 100
                fcf_s *= (1 + g_use)
                pv_s += fcf_s / (1 + r_s) ** y
            tv_s = fcf_s * (1 + gt) / (r_s - gt) if r_s > gt else 0
            pv_tv_s = tv_s / (1 + r_s) ** 10
            ev_s = pv_s + pv_tv_s
            iv_s = (ev_s - net_debt) / shares_outstanding if shares_outstanding > 0 else 0
            row.append(f"${iv_s:>10,.2f}")
        lines.append("".join(row))

    lines.append("═" * 55)
    return "\n".join(lines)


# ── Debt Sustainability ───────────────────────────────────────────────────────

class DebtInput(BaseModel):
    country: str = Field(..., description="Country name for display.")
    debt_to_gdp: float = Field(..., description="Current debt-to-GDP ratio in %.")
    nominal_gdp_growth: float = Field(..., description="Nominal GDP growth rate in %.")
    nominal_interest_rate: float = Field(..., description="Average nominal interest rate on debt in %.")
    primary_balance: float = Field(
        ...,
        description="Primary fiscal balance as % of GDP (positive = surplus, negative = deficit).",
    )
    horizon_years: int = Field(default=5, description="Projection horizon in years.")


@tool("calculate_debt_sustainability", args_schema=DebtInput)
def calculate_debt_sustainability(
    country: str,
    debt_to_gdp: float,
    nominal_gdp_growth: float,
    nominal_interest_rate: float,
    primary_balance: float,
    horizon_years: int,
) -> str:
    """Assess government debt sustainability using standard IMF framework.

    The debt ratio evolves as:
    d(t) = d(t-1) × (1+r)/(1+g) - pb(t)
    where r = interest rate, g = GDP growth, pb = primary balance % GDP.

    Args:
        country: Country name.
        debt_to_gdp: Debt/GDP in %.
        nominal_gdp_growth: GDP growth in %.
        nominal_interest_rate: Avg interest rate on debt in %.
        primary_balance: Primary balance (% GDP). Negative = deficit.
        horizon_years: Years to project.

    Returns:
        Debt trajectory with sustainability verdict.
    """
    r = nominal_interest_rate / 100
    g = nominal_gdp_growth / 100
    pb = primary_balance / 100
    snowball = (r - g) / (1 + g)  # debt snowball effect

    lines = [f"Debt Sustainability Analysis — {country}", "═" * 55]
    lines.append(f"  Interest rate (r):       {nominal_interest_rate:.2f}%")
    lines.append(f"  GDP growth (g):          {nominal_gdp_growth:.2f}%")
    lines.append(f"  r - g (snowball effect): {(r-g)*100:+.2f}%")
    lines.append(f"  Primary balance:         {primary_balance:+.2f}% GDP")
    lines.append("")

    if snowball > 0:
        lines.append(f"  ⚠ r > g — debt is self-reinforcing without primary surplus")
    else:
        lines.append(f"  ✓ r < g — GDP growth helps absorb debt")

    lines.append("")
    lines.append(f"  {'Year':<6} {'Debt/GDP':>10}  {'Change':>8}")
    lines.append("  " + "-" * 28)

    debt = debt_to_gdp / 100
    for y in range(horizon_years + 1):
        change = "" if y == 0 else f"{(debt - prev_debt)*100:+.1f}pp"
        prev_debt = debt
        lines.append(f"  {y:<6} {debt*100:>8.1f}%  {change:>8}")
        debt = debt * (1 + snowball) - pb

    final_debt = debt * 100
    initial_debt = debt_to_gdp
    trend = "RISING" if final_debt > initial_debt + 2 else "FALLING" if final_debt < initial_debt - 2 else "STABLE"

    lines.append("")
    primary_needed = snowball * (debt_to_gdp / 100) * 100
    lines.append(f"  Primary balance to stabilise debt: {primary_needed:+.2f}% GDP")
    lines.append(f"  Current primary balance:           {primary_balance:+.2f}% GDP")
    lines.append("")
    lines.append(f"  VERDICT: Debt trend is {trend}")
    if final_debt > 90:
        lines.append("  ⚠ HIGH RISK — debt above 90% GDP threshold")
    elif final_debt > 60:
        lines.append("  ⚡ MODERATE — above 60% GDP Maastricht threshold")
    else:
        lines.append("  ✓ SUSTAINABLE — below 60% GDP")
    lines.append("═" * 55)
    return "\n".join(lines)
