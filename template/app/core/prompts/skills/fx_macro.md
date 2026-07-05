# Skill: FX & Macro Analysis (Blueprint B)

Full workflow for FX forecasts, macro analysis, and capital flow direction.

## Step 0 — Locale detection (CRITICAL)
Detect user's home currency from message language:
- Ukrainian → home = UAH, pair = USD/UAH, spot in 40–60 range
- Polish → home = PLN
- German/Austrian → home = EUR
- British English → home = GBP
- Default → ask or use USD

NEVER use PLN/CZK/HUF data for Ukrainian queries.

## Mandatory workflow

**Step 1 — US Macro baseline**
```
get_us_macro_data(["fed_funds_rate","us_cpi_yoy","us_10y_yield","us_2y_yield","dollar_index","vix"])
```

**Step 2 — FX spot rates**
```
get_fx_rates("USD", [home_currency, "EUR", "GBP"])
```
Sanity check: USD/UAH must be 40–60. If result is 4–6 → order-of-magnitude error, retry.

**Step 3 — Yield curve (for recession risk)**
```
get_yield_curve("US")
```
2Y > 10Y inversion → recession signal within 12–18 months.

**Step 4 — IRP fair value**
```
calculate_irp(
  spot_rate=<from step 2>,
  rate_domestic=<home central bank rate>,
  rate_foreign=<fed_funds_rate from step 1>,
  inflation_domestic=<home CPI>,
  inflation_foreign=<us_cpi_yoy from step 1>,
  horizon_months=<6 or 12>,
  pair_name="USD/UAH"
)
```
Ukraine defaults: rate_domestic=13.5, inflation_domestic=12.0 (update from duckduckgo_search if needed).

**Step 5 — Real yields (capital flow direction)**
```
calculate_real_yields([
  {"name":"Ukraine","nominal_yield":13.5,"inflation":12.0,"currency":"UAH"},
  {"name":"US","nominal_yield":<fed_rate>,"inflation":<us_cpi>,"currency":"USD"}
])
```

**Step 6 — Verdict with 3 scenarios**
- Base: IRP average
- Bull (home currency strengthens): higher domestic rate or lower inflation
- Bear (home currency weakens): fiscal deficit widens, geopolitical shock

## Geopolitical risk factors (Ukraine-specific)
When analyzing UAH: consider
- NBU FX interventions (uses USD reserves to defend UAH)
- International aid tranches (IMF, EU, US) — UAH-positive
- Infrastructure attacks → industrial output drop → trade deficit widening → UAH-negative
Use `duckduckgo_search` for latest news on these factors.

## Output financial_data for forecast
```json
{"currency_pair":"USD/UAH","rate":44.92,"rate_forecast":46.92,"rate_bull":45.5,"rate_bear":49.0,
 "change_pct":4.44,"source":"NBU","model_used":"IRP","horizon_months":6}
```
