# Skill: Equity Analysis (Blueprint A)

Full due diligence workflow for stocks, ADRs, and public equities.

## Mandatory 4-step workflow (run IN ORDER, never skip)

**Step 1 — Market data**
```
get_market_data(ticker)
```
Returns: price, P/E, forward P/E, EPS, revenue, margins, beta, market cap, 5 recent headlines.
Never use memorised figures — always call this first.

**Step 2 — Macro context**
```
get_us_macro_data(["fed_funds_rate","us_10y_yield","vix","us_cpi_yoy","credit_spread_hy"])
```
Used for: discount rate justification, risk-off detection (VIX > 25 = elevated), credit environment.

**Step 3 — Intrinsic value**
```
calculate_dcf(
  current_fcf=<from step 1 or sandbox>,
  growth_rate_y1_5=<analyst estimate>,
  growth_rate_y6_10=<conservative>,
  terminal_growth=2.5,
  wacc=<10y yield + equity risk premium>,
  shares_outstanding=<from step 1>,
  net_debt=<total debt - cash>,
  ticker=ticker
)
```
If FCF is not in market_data output → use `execute_python_sandbox` to calculate from revenue × FCF margin.

**Step 4 — Structured report**
```
generate_dd_report(ticker=ticker, risk_profile=<user risk profile or "moderate">)
```
Returns APPROVED/REJECTED with justification.

## Valuation decision tree

| Condition | Verdict |
|---|---|
| Price < DCF fair value AND VIX < 20 AND margins stable | APPROVED |
| Price > DCF fair value × 1.2 | REJECTED (overvalued) |
| P/E > sector avg × 1.5 AND growth < 10% | REJECTED (expensive/low growth) |
| VIX > 30 AND credit spread HY > 500bp | REJECTED (macro risk) |

## Output financial_data for equity
```json
{"ticker":"NVDA","price":131.40,"market_cap":"$3.2T","pe_ratio":35.2,"verdict":"APPROVED","confidence":0.78}
```
