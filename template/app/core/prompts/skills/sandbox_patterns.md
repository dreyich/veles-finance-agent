# Skill: Python Sandbox — Calculation Templates

Use `execute_python_sandbox` for any calculation not covered by built-in tools.

## Rules
- Always `print()` results explicitly
- Include all imports inside the code string
- Allowed: math, statistics, json, datetime, re, numpy (if available), pandas (if available)
- FORBIDDEN: os, subprocess, socket, requests, urllib, eval, exec, open()

## Template: Monte Carlo simulation
```python
import random
import statistics

random.seed(42)
n_simulations = 10000
spot = 44.92
daily_vol = 0.005  # 0.5% daily volatility

outcomes = []
for _ in range(n_simulations):
    rate = spot
    for day in range(180):  # 6 months
        rate *= (1 + random.gauss(0, daily_vol))
    outcomes.append(rate)

outcomes.sort()
print(f"Monte Carlo 6M USD/UAH (n={n_simulations}):")
print(f"  Median:  {statistics.median(outcomes):.4f}")
print(f"  P10:     {outcomes[int(0.1*n_simulations)]:.4f}")
print(f"  P90:     {outcomes[int(0.9*n_simulations)]:.4f}")
print(f"  P5 VaR:  {outcomes[int(0.05*n_simulations)]:.4f}")
```

## Template: FCF calculation from income statement
```python
revenue = 60.9e9       # USD
operating_margin = 0.614
capex_pct_revenue = 0.028
tax_rate = 0.132

ebit = revenue * operating_margin
nopat = ebit * (1 - tax_rate)
capex = revenue * capex_pct_revenue
# Approximate FCF (ignoring working capital changes)
fcf = nopat - capex
print(f"Estimated FCF: ${fcf/1e9:.2f}B")
print(f"FCF Margin: {fcf/revenue*100:.1f}%")
```

## Template: Sensitivity table
```python
base_rate = 44.92
scenarios = [
    ("Bull (NBU +2pp, inflation -3pp)", 0.155, 0.09, 0.0433, 0.024),
    ("Base (current)", 0.135, 0.12, 0.0433, 0.024),
    ("Bear (NBU -2pp, inflation +5pp)", 0.115, 0.17, 0.0433, 0.024),
]
t = 6/12  # 6 months

print(f"{'Scenario':<40} {'IRP Rate':>10} {'Change':>8}")
print("-" * 60)
for name, rd, pid, rf, pif in scenarios:
    irp = base_rate * ((1+rd)**t) / ((1+rf)**t)
    ppp = base_rate * ((1+pid)**t) / ((1+pif)**t)
    avg = (irp + ppp) / 2
    chg = (avg - base_rate) / base_rate * 100
    print(f"{name:<40} {avg:>10.4f} {chg:>+7.2f}%")
```
