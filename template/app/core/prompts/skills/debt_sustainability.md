# Skill: Government Debt & Fiscal Sustainability (Blueprint C)

Workflow for sovereign debt analysis using IMF r-vs-g framework.

## Data gathering
```
get_global_macro_data(country=<country>, indicators=["debt_to_gdp","gdp_growth","inflation"])
get_us_macro_data(["us_10y_yield"])  # benchmark for EM spreads
```

## Core calculation
```
calculate_debt_sustainability(
  country=<name>,
  debt_to_gdp=<from world bank>,
  nominal_gdp_growth=<gdp_growth + inflation>,
  nominal_interest_rate=<avg sovereign bond yield>,
  primary_balance=<fiscal balance % GDP — negative = deficit>,
  horizon_years=5
)
```

## Interpretation
- **r > g (snowball effect)**: debt self-reinforces → need primary surplus to stabilise
- **r < g**: GDP growth absorbs debt → sustainable even with small deficits
- Debt > 90% GDP: HIGH RISK threshold (Reinhart-Rogoff)
- Debt > 60% GDP: Maastricht threshold for EU countries

## Ukraine-specific context
- War economy: high deficit (~20% GDP) is expected during active conflict
- Sustainability hinges on international grants (not loans) from IMF/EU/US
- Post-war reconstruction scenario materially changes r-g dynamics
- Use `duckduckgo_search("Ukraine IMF program fiscal 2025")` for latest data

## Output
```json
{"intent":"macro","text_response":"Debt trajectory: RISING / STABLE / FALLING. Primary balance gap: X% GDP.","financial_data":null}
```
