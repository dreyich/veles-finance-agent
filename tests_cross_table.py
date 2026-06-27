"""
Cross-table tests: відповідь неможлива без поєднання даних з кількох розділів
Всі дані — реальні з Tesla 10-K FY2023 (SEC EDGAR)
"""
import os, json
from groq import Groq

client = Groq(api_key=os.environ["OPENAI_API_KEY"])
MODEL = "llama-3.3-70b-versatile"
SCORES = []

def ask(text, fields, sys_hint=""):
    sys_msg = "Extract and reason across multiple financial tables from 10-K filing. Return JSON only. All values as numbers. Perform calculations when needed."
    if sys_hint:
        sys_msg += " " + sys_hint
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": f"{text}\n\nFields needed: {fields}"}
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        print(f"  [API ERROR]: {str(e)[:200]}")
        return {}

def check(name, result, truth, tol=1.0):
    correct = wrong = 0
    errors = []
    for field, expected in truth.items():
        got = result.get(field, "MISSING")
        if expected is None:
            ok = got is None or got == 0
        elif isinstance(expected, str):
            ok = str(got).strip().lower() == expected.lower()
        elif isinstance(expected, (int, float)) and isinstance(got, (int, float)):
            ok = abs(float(got) - float(expected)) <= tol
        else:
            ok = str(got) == str(expected)
        if ok:
            correct += 1
        else:
            wrong += 1
            errors.append(f"    {field}: expected={expected}, got={got}")
    pct = correct / (correct + wrong) * 100
    tag = "OK" if pct == 100 else ("PARTIAL" if pct >= 70 else "FAIL")
    print(f"\n{'='*65}")
    print(f"{name}")
    print(f"SCORE: {correct}/{correct+wrong} = {pct:.0f}%  [{tag}]")
    for e in errors:
        print(e)
    SCORES.append((name, pct))


# ═══════════════════════════════════════════════════════════════
# CT1: AUTOMOTIVE SEGMENT vs INCOME STATEMENT — чому цифри різні?
#
# ТАБЛИЦЯ 1 (Income Statement, R5):
#   Automotive revenues = $82,419M  (ТІЛЬКИ авто, без сервісів)
#   Services and other  = $8,319M   (окремий рядок)
#
# ТАБЛИЦЯ 2 (Segments Note, R26):
#   Automotive SEGMENT revenues = $90,738M  (включає сервіси!)
#
# Питання: чому $82,419 + $8,319 = $90,738 — і яка різниця між
#           gross margin автомобільного сегменту vs консолідованою?
# ═══════════════════════════════════════════════════════════════

CT1_TEXT = """
Tesla, Inc. — FY2023 ($ in Millions)

TABLE 1: Consolidated Statements of Operations
  Automotive revenues (sales + regulatory credits + leasing):  $82,419
    - Automotive sales:               $78,509
    - Automotive regulatory credits:   $1,790
    - Automotive leasing:              $2,120
  Energy generation and storage:       $6,035
  Services and other:                  $8,319
  TOTAL revenues:                     $96,773

  Cost of revenues - Automotive:      $66,389
  Cost of revenues - Energy:           $4,894
  Cost of revenues - Services:         $7,830
  TOTAL cost of revenues:             $79,113
  CONSOLIDATED gross profit:          $17,660

TABLE 2: Segment Reporting Note
  Automotive SEGMENT revenues:        $90,738  <- includes Services and other
  Automotive SEGMENT gross profit:    $16,519
  Automotive SEGMENT gross margin %:  (to be calculated)

  Energy generation & storage revenues: $6,035
  Energy generation & storage gross profit: $1,141
  Energy gross margin %: (to be calculated)

Note from management: "The automotive segment includes... services and other,
which includes sales of used vehicles, non-warranty after-sales vehicle services..."
Therefore: Automotive segment revenue = $82,419 (auto) + $8,319 (services) = $90,738
"""

r = ask(CT1_TEXT, """
automotive_income_stmt_revenue,
services_revenue_income_stmt,
automotive_segment_total_revenue,
reconciliation_check (auto + services should equal segment total),
automotive_segment_gross_profit,
automotive_segment_gross_margin_pct,
energy_segment_gross_profit,
energy_segment_gross_margin_pct,
consolidated_gross_margin_pct,
which_segment_higher_margin,
energy_gross_profit_change_2022_to_2023 (use: 2022 energy GP was $288M, 2023 is $1141M)
""")
check("CT1: Automotive segment vs Income Statement revenue reconciliation", r, {
    "automotive_income_stmt_revenue": 82419,
    "services_revenue_income_stmt": 8319,
    "automotive_segment_total_revenue": 90738,
    "reconciliation_check": 90738,           # 82419 + 8319 = 90738
    "automotive_segment_gross_profit": 16519,
    "automotive_segment_gross_margin_pct": round(16519/90738*100, 1),  # 18.2%
    "energy_segment_gross_profit": 1141,
    "energy_segment_gross_margin_pct": round(1141/6035*100, 1),        # 18.9%
    "consolidated_gross_margin_pct": round(17660/96773*100, 1),        # 18.3%
    "which_segment_higher_margin": "energy",  # 18.9% > 18.2%
    "energy_gross_profit_change_2022_to_2023": 1141 - 288,            # = 853
}, tol=0.2)


# ═══════════════════════════════════════════════════════════════
# CT2: DEBT NOTE + INCOME STATEMENT — interest coverage ratio
#      + debt type classification (recourse vs non-recourse)
#
# Дані з ДВОХ таблиць:
# - Interest expense: Income Statement (R5)
# - Debt breakdown: Debt Note (R19)
# ═══════════════════════════════════════════════════════════════

CT2_TEXT = """
Tesla, Inc. — FY2023 Cross-Table Analysis ($ in Millions)

TABLE 1: Income Statement (excerpts)
  Income from operations:         $8,891
  Interest income:                $1,066
  Interest expense:                ($156)
  Income before income taxes:     $9,973
  (Benefit from) income taxes:   ($5,001)
  Net income:                    $14,974

TABLE 2: Debt and Finance Leases Note (as of December 31, 2023)
  Recourse debt:
    2024 Notes (2.00%, matures May 2024):   Current $37M, Long-term $0
    Solar Bonds (4.70-5.75%):               Current $0, Long-term $7M
    Other:                                  Current $0, Long-term $28M (matures Dec 2026)
    RCF Credit Agreement (unused, Jan 2028): Committed $5,000M (undrawn)
    Total recourse debt:                    Current $37M + Long-term $7M = $44M

  Non-recourse debt:
    Automotive Asset-backed Notes (0.60-6.57%): Current $1,906M, Long-term $2,337M = $4,243M
    Solar Asset-backed Notes (4.80%):           Current $4M, Long-term $8M = $12M (wait, text says 13)
    Cash Equity Debt (5.25-5.81%):              Current $28M, Long-term $330M = $358M (text: 367)
    Total non-recourse debt:                    Current $1,938M, Long-term $2,675M = $4,613M (text: 4,639)

  Total debt (recourse + non-recourse):   Current $1,975M, Long-term $2,682M = $4,657M (text: $4,683)
  Finance leases:                         Current $398M, Long-term $175M = $573M (text: total debt+leases $2,373+$2,857=$5,230)

  As of Dec 31, 2022 (prior year):
    Total debt:                           $2,061M
    Finance leases:                       $486M + $568M = $1,054M
    Total debt and leases 2022:           $2,599M
"""

r = ask(CT2_TEXT, """
operating_income_2023,
interest_expense_2023,
interest_coverage_ratio (operating_income / abs(interest_expense)),
total_recourse_debt_2023,
total_nonrecourse_debt_2023,
total_debt_excluding_leases_2023,
total_finance_leases_2023,
total_debt_and_leases_2023,
debt_change_yoy (total_debt_2023 minus total_debt_2022),
pct_nonrecourse_of_total_debt,
notes_maturing_2024_amount,
effective_tax_rate_pct (income_tax / income_before_tax * 100, note: benefit means negative tax)
""")
check("CT2: Debt note + Income Statement — coverage ratio + recourse split + effective tax", r, {
    "operating_income_2023": 8891,
    "interest_expense_2023": -156,
    "interest_coverage_ratio": round(8891/156, 1),    # 57.0x — requires cross-table
    "total_recourse_debt_2023": 44,                   # 37+7 = 44
    "total_nonrecourse_debt_2023": 4639,
    "total_debt_excluding_leases_2023": 4683,
    "total_finance_leases_2023": 573,                 # 398+175
    "total_debt_and_leases_2023": 5230,               # 2373+2857
    "debt_change_yoy": 4683 - 2061,                   # = +2622 increase
    "pct_nonrecourse_of_total_debt": round(4639/4683*100, 1),  # 99.1%
    "notes_maturing_2024_amount": 37,                 # 2024 Notes current portion
    "effective_tax_rate_pct": round(-5001/9973*100, 1),  # -50.1% (benefit!)
}, tol=0.2)


# ═══════════════════════════════════════════════════════════════
# CT3: GEOGRAPHIC + SEGMENT — частка Китаю в автомобільному сегменті
#
# TABLE 1 (Segments): automotive segment = $90,738M
# TABLE 2 (Geographic): China = $21,745M total (всі сегменти)
# TABLE 3 (Income Stmt): Energy = $6,035M
#
# Питання: яка частка виручки в Китаї припадає на автомобілі?
# Відповідь: потрібно відняти енергетичний сегмент з китайської виручки
# (припускаючи, що майже вся китайська виручка — авто)
# ═══════════════════════════════════════════════════════════════

CT3_TEXT = """
Tesla, Inc. — FY2023 Geographic and Segment Data ($ in Millions)

TABLE 1: Revenue by Segment
  Automotive segment (incl. services): $90,738
  Energy generation and storage:        $6,035
  TOTAL:                               $96,773

TABLE 2: Revenue by Geography (all segments combined)
  United States:      $45,235  (46.7% of total)
  China:              $21,745  (22.5% of total)
  Other international: $29,793  (30.8% of total)
  TOTAL:              $96,773

TABLE 3: Long-lived Assets by Geography
  United States:      $26,629
  Germany:             $4,258
  China:               $2,820
  Other international: $1,247
  TOTAL:              $34,954

Note: Tesla does not separately disclose segment revenue by geography.
China revenue of $21,745M includes both automotive and energy products sold in China.
Germany long-lived assets primarily represent the Gigafactory Berlin.
"""

r = ask(CT3_TEXT, """
china_revenue_total,
china_revenue_pct_of_total,
us_revenue_pct_of_total,
automotive_segment_pct_of_total_revenue,
china_longterm_assets,
germany_longterm_assets,
us_longterm_assets,
china_assets_pct_of_total_assets,
germany_assets_pct_of_total_assets,
international_revenue_total (China + Other international),
international_revenue_pct,
us_china_revenue_gap (US minus China),
can_determine_china_automotive_only (yes/no - is it possible to separate?)
""")
check("CT3: Geographic x Segment cross-analysis — China/US split + asset distribution", r, {
    "china_revenue_total": 21745,
    "china_revenue_pct_of_total": round(21745/96773*100, 1),   # 22.5%
    "us_revenue_pct_of_total": round(45235/96773*100, 1),      # 46.7%
    "automotive_segment_pct_of_total_revenue": round(90738/96773*100, 1),  # 93.8%
    "china_longterm_assets": 2820,
    "germany_longterm_assets": 4258,
    "us_longterm_assets": 26629,
    "china_assets_pct_of_total_assets": round(2820/34954*100, 1),  # 8.1%
    "germany_assets_pct_of_total_assets": round(4258/34954*100, 1),  # 12.2%
    "international_revenue_total": 21745 + 29793,  # = 51538
    "international_revenue_pct": round((21745+29793)/96773*100, 1),  # 53.3%
    "us_china_revenue_gap": 45235 - 21745,  # = 23490
    "can_determine_china_automotive_only": "no",  # Tesla doesn't disclose this
}, tol=0.2)


# ═══════════════════════════════════════════════════════════════
# CT4: SEGMENT GROSS PROFIT + INCOME STATEMENT — reconciliation trap
#
# Пастка: суми сегментів не збігаються з консолідованою завдяки
# корпоративним витратам які не розподіляються між сегментами
# ═══════════════════════════════════════════════════════════════

CT4_TEXT = """
Tesla, Inc. — FY2023 Segment-to-Consolidated Reconciliation ($ in Millions)

TABLE 1: Segment Results
  Automotive segment gross profit:              $16,519
  Energy generation and storage gross profit:    $1,141
  Sum of segment gross profits:                 $17,660

TABLE 2: Consolidated Income Statement
  Total revenues:          $96,773
  Total cost of revenues:  $79,113
  Consolidated gross profit: $17,660

  Operating expenses (NOT included in segment gross profit):
    Research and development:              $3,969
    Selling, general and administrative:   $4,800
    Restructuring and other:                   $0
    Total operating expenses:              $8,769

  Income from operations:   $8,891

TABLE 3: Inventory by Segment (Balance Sheet Note)
  Automotive inventory:                   $11,139
  Energy generation and storage inventory: $2,487
  Total inventory:                         $13,626

Note: Tesla's CODM evaluates segments on gross profit only.
R&D and SG&A are corporate-level expenses not allocated to segments.
"""

r = ask(CT4_TEXT, """
segment_gp_sum,
consolidated_gp,
gp_reconciliation_difference (segment sum minus consolidated - should be zero),
automotive_gp_pct_of_consolidated_gp,
energy_gp_pct_of_consolidated_gp,
consolidated_operating_income,
gp_to_operating_income_bridge (what explains the difference: $17660 GP vs $8891 OpIncome),
unallocated_opex_total,
automotive_inventory,
energy_inventory,
automotive_inventory_as_pct_of_segment_revenue,
energy_inventory_turns (energy_revenue / energy_inventory)
""")
check("CT4: Segment GP reconciliation + unallocated opex + inventory turns cross-table", r, {
    "segment_gp_sum": 17660,          # 16519 + 1141
    "consolidated_gp": 17660,
    "gp_reconciliation_difference": 0,  # perfect reconciliation
    "automotive_gp_pct_of_consolidated_gp": round(16519/17660*100, 1),  # 93.5%
    "energy_gp_pct_of_consolidated_gp": round(1141/17660*100, 1),       # 6.5%
    "consolidated_operating_income": 8891,
    "gp_to_operating_income_bridge": 17660 - 8891,  # = 8769 (= total opex)
    "unallocated_opex_total": 8769,    # R&D + SGA = bridge from GP to OpIncome
    "automotive_inventory": 11139,
    "energy_inventory": 2487,
    "automotive_inventory_as_pct_of_segment_revenue": round(11139/90738*100, 1),  # 12.3%
    "energy_inventory_turns": round(6035/2487, 2),   # 2.43x — cross-table calc
}, tol=0.2)


# ═══════════════════════════════════════════════════════════════
# CT5: MULTI-YEAR TREND + SEGMENT MARGIN EXPANSION
#
# Найскладніший: потрібно дістати дані з 3 різних років з 2 таблиць
# і порахувати зміну маржі в кожному сегменті
# ═══════════════════════════════════════════════════════════════

CT5_TEXT = """
Tesla, Inc. — Multi-Year Segment Analysis ($ in Millions)

TABLE 1: Segment Revenue and Gross Profit (from Segment Note)
                        2023        2022        2021
Automotive segment:
  Revenue             $90,738     $77,553     $51,034
  Gross profit        $16,519     $20,565     $13,735

Energy segment:
  Revenue              $6,035      $3,909      $2,789
  Gross profit          $1,141        $288       ($129)

TABLE 2: Consolidated Summary (from Income Statement)
                        2023        2022        2021
Total revenues         $96,773     $81,462     $53,823
Consolidated GP        $17,660     $20,853     $13,606
Operating income        $8,891     $13,656      $6,523
Net income             $14,974     $12,587      $5,644

Notes:
- Energy segment had NEGATIVE gross profit in 2021 ($129M loss)
- Automotive segment gross margin DECLINED from 2022 to 2023
  despite revenue growth
- Energy segment turned profitable in 2022 and expanded margins in 2023
"""

r = ask(CT5_TEXT, """
auto_gm_pct_2023,
auto_gm_pct_2022,
auto_gm_pct_2021,
auto_gm_change_2022_to_2023_pp (percentage points),
energy_gm_pct_2023,
energy_gm_pct_2022,
energy_gm_pct_2021,
energy_turned_profitable_year,
consolidated_gm_pct_2023,
consolidated_gm_pct_2022,
which_segment_margin_declined_2022_to_2023,
total_revenue_cagr_2021_to_2023_pct,
net_income_2022_vs_2023_change (2023 minus 2022),
automotive_revenue_growth_2022_to_2023_pct
""")
check("CT5: 3-year segment margin trends + CAGR + margin decline identification", r, {
    "auto_gm_pct_2023": round(16519/90738*100, 1),   # 18.2%
    "auto_gm_pct_2022": round(20565/77553*100, 1),   # 26.5%
    "auto_gm_pct_2021": round(13735/51034*100, 1),   # 26.9%
    "auto_gm_change_2022_to_2023_pp": round(16519/90738*100 - 20565/77553*100, 1),  # -8.3pp
    "energy_gm_pct_2023": round(1141/6035*100, 1),   # 18.9%
    "energy_gm_pct_2022": round(288/3909*100, 1),    # 7.4%
    "energy_gm_pct_2021": round(-129/2789*100, 1),   # -4.6%
    "energy_turned_profitable_year": 2022,
    "consolidated_gm_pct_2023": round(17660/96773*100, 1),  # 18.3%
    "consolidated_gm_pct_2022": round(20853/81462*100, 1),  # 25.6%
    "which_segment_margin_declined_2022_to_2023": "automotive",
    "total_revenue_cagr_2021_to_2023_pct": round(((96773/53823)**0.5 - 1)*100, 1),  # 34.1%
    "net_income_2022_vs_2023_change": 14974 - 12587,   # = +2387
    "automotive_revenue_growth_2022_to_2023_pct": round((90738-77553)/77553*100, 1),  # 17.0%
}, tol=0.3)


# ═══════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════
print("\n" + "="*65)
print("CROSS-TABLE TEST RESULTS")
print("="*65)
for name, pct in SCORES:
    tag = "OK" if pct==100 else ("PARTIAL" if pct>=70 else "FAIL")
    print(f"  {pct:5.1f}%  [{tag}]  {name[:55]}")
avg = sum(s for _,s in SCORES) / len(SCORES)
perfect = len([s for _,s in SCORES if s==100])
print(f"\nAVERAGE: {avg:.1f}%  |  Perfect: {perfect}/{len(SCORES)}")
print(f"Single-table avg (previous tests): ~88%")
print(f"Cross-table avg: {avg:.1f}%  <-- gap?")
