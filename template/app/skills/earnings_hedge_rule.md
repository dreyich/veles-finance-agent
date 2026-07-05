---
skill: earnings_hedge_rule
created_at: 2026-06-23T12:13:09Z
---

## Rule
Mandatory options hedge for any single position that is either >5% of portfolio value or has IV Rank >50% before a binary event (earnings, FDA decision, major regulatory announcement). Hedge must be placed before market close at least one trading day prior to the event.

## Why
You lost 30% of portfolio by holding a high-volatility tech stock through an earnings report without a protective options hedge. Binary events can produce rapid, large moves driven by realized volatility far exceeding implied expectations. Concentrated exposure and lack of predefined cost limits allowed outsized drawdown. A mandatory hedge reduces event-driven tail risk, enforces discipline, and caps loss to a predefined, acceptable amount.

## Action Steps
1. Flag positions: Automated or manual daily scan to flag any position meeting either condition: position size >5% of portfolio OR IV Rank >50% (measured over 1 year or user-preferred lookback).
2. Check event calendar: For flagged positions, check 0–7 day event window for earnings, FDA or major catalysts. Use official company filings and reputable calendars.
3. Hedge selection (choose one):
   - Protective puts: Buy ATM to slightly OTM puts expiring 1–2 weeks after the event. Target delta between 0.20–0.35 depending on cost tolerance.
   - Collars: Sell OTM calls and buy OTM puts to limit net premium cost. Ensure short call strike is sufficiently OTM to preserve upside you want to keep.
4. Cost cap: Cap hedge cost at 0.5%–2% of portfolio per large position. If cost exceeds cap, reduce position size or use less expensive collar structure.
5. Execution timing: Execute hedge before market close at least one trading day prior to the event; if implied volatility is rising, consider earlier execution.
6. Position sizing fallback: If unable/unwilling to hedge within cost cap, reduce position to below 5% of portfolio before event to avoid mandatory hedge requirement.
7. Post-event review: After event, document outcome, actual P/L, hedge effectiveness, and update IV rank measurement and cost thresholds if needed.
8. Recordkeeping: Save trade tickets, timestamps, and reasons for deviating from the rule (if any). Any deviation requires manager sign-off.

## Example
Portfolio $100,000. Holding $8,000 position (8%): company X with IV Rank 65%, earnings in 3 days.
- Flagged because position >5% and IV Rank >50%.
- Buy 1 protective put 1 week out, delta ~0.30, costing $150 (0.15% of portfolio). Cost within 0.5%–2% cap: proceed.
- If put cost were $1,200 (>1.2% of portfolio) then either use a collar to reduce net cost or trim position to <5% prior to event.

Notes: This is a mandatory risk-control rule designed to prevent large event-driven drawdowns. The rule balances cost vs protection and requires discipline to follow or document exceptions.
