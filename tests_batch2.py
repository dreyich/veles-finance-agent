"""
10 targeted tests covering different financial document edge cases
"""
import os, json
from groq import Groq

client = Groq(api_key=os.environ["OPENAI_API_KEY"])
MODEL = "llama-3.3-70b-versatile"

def run_test(name, text, fields_str, ground_truth, tolerance=1.0):
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "Extract financial data from 10-K/10-Q filings. Return JSON only. All values must be numbers (integers or floats), never expressions. Compute calculations and return the final number. Negative values for losses/deductions. Null if cannot be determined."},
                {"role": "user", "content": f"Extract from financial filing:\n\n{text}\n\nFields needed: {fields_str}\n\nIMPORTANT: Return only computed numeric values, never math expressions like '-37120 - 45740'. Compute and return the result."}
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        result = json.loads(resp.choices[0].message.content)
    except Exception as e:
        err_str = str(e)
        # Try to extract failed_generation from error
        if "failed_generation" in err_str:
            import re
            fg = re.search(r"'failed_generation': '(.+)'}", err_str, re.DOTALL)
            raw = fg.group(1) if fg else "{}"
            print(f"\n  [API ERROR - invalid JSON generated]: {raw[:200]}")
        else:
            print(f"\n  [API ERROR]: {err_str[:200]}")
        result = {}
    correct = wrong = 0
    errors = []
    for field, expected in ground_truth.items():
        got = result.get(field, "MISSING")
        if expected is None:
            ok = got is None or got == "null" or got == 0
        elif isinstance(expected, (int, float)) and isinstance(got, (int, float)):
            ok = abs(float(got) - float(expected)) <= tolerance
        elif isinstance(expected, str):
            ok = str(got).strip().lower() == expected.strip().lower()
        else:
            ok = str(got) == str(expected)
        if ok:
            correct += 1
        else:
            wrong += 1
            errors.append(f"{field}: expected={expected}, got={got}")
    score = correct / (correct + wrong) * 100
    status = "OK" if score == 100 else ("PARTIAL" if score >= 70 else "FAIL")
    print(f"\n{'='*65}")
    print(f"TEST: {name}")
    print(f"SCORE: {correct}/{correct+wrong} = {score:.0f}%  [{status}]")
    if errors:
        for e in errors:
            print(f"  WRONG: {e}")
    return score


# ─────────────────────────────────────────────────────────────
# T6: Parenthetical negatives — (1,234) means -1,234
# ─────────────────────────────────────────────────────────────
T6_TEXT = """
CONSOLIDATED STATEMENTS OF OPERATIONS (in thousands)
                                    FY2023          FY2022
Revenue                             $842,310        $761,240
Cost of goods sold                  (489,420)       (451,830)
Gross profit                         352,890         309,410
Operating expenses:
  Research and development          (98,430)        (84,210)
  Sales and marketing               (112,840)       (101,560)
  General and administrative         (44,320)        (38,910)
  Impairment of long-lived assets    (23,500)              —
Total operating expenses            (279,090)       (224,680)
Operating income                      73,800          84,730
Interest income                        8,420           4,310
Interest expense                     (31,240)        (29,880)
Other income (expense), net           (2,140)          1,830
Income before taxes                   48,840          60,990
Income tax expense                   (11,720)        (15,250)
Net income                          $ 37,120        $ 45,740
"""

T6_TRUTH = {
    "revenue_fy2023": 842310,
    "cogs_fy2023": -489420,            # negative
    "gross_profit_fy2023": 352890,
    "rd_expense_fy2023": -98430,       # negative
    "impairment_fy2023": -23500,       # negative, zero in FY2022
    "impairment_fy2022": 0,            # — means zero
    "operating_income_fy2023": 73800,
    "interest_expense_fy2023": -31240, # negative
    "net_income_fy2023": 37120,
    "net_income_fy2022": 45740,
    "net_income_change": 37120 - 45740,  # = -8620, requires calc
}
run_test("T6: Parenthetical negatives + dash-as-zero + YoY change",
         T6_TEXT, "revenue_fy2023, cogs_fy2023, gross_profit_fy2023, rd_expense_fy2023, impairment_fy2023, impairment_fy2022, operating_income_fy2023, interest_expense_fy2023, net_income_fy2023, net_income_fy2022, net_income_change",
         T6_TRUTH)


# ─────────────────────────────────────────────────────────────
# T7: Multi-currency table
# ─────────────────────────────────────────────────────────────
T7_TEXT = """
NOTE 14 — FOREIGN OPERATIONS (in millions)

Revenue by geography and functional currency:
                        USD         EUR         GBP         JPY (billions)
North America           $2,341.2    —           —           —
Europe                  $891.4      €823.1      £187.3      —
Japan                   $234.7      —           —           ¥34,821
Rest of World           $445.8      —           —           —
Total reported (USD)    $3,913.1    —           —           —

Average exchange rates used: EUR/USD 1.0823, GBP/USD 1.2714, JPY/USD 0.00674

Note: JPY amounts shown in billions. USD equivalent calculated at average rate.
Japan USD equivalent = ¥34,821B × 0.00674 = $234.7M (rounded).
"""

T7_TRUTH = {
    "north_america_revenue_usd": 2341.2,
    "europe_revenue_usd": 891.4,
    "europe_revenue_eur": 823.1,
    "europe_revenue_gbp": 187.3,
    "japan_revenue_usd": 234.7,
    "japan_revenue_jpy_billions": 34821,   # TRAP: unit is billions not millions
    "total_revenue_usd": 3913.1,
    "eur_usd_rate": 1.0823,
    "gbp_usd_rate": 1.2714,
    "jpy_usd_rate": 0.00674,
}
run_test("T7: Multi-currency + unit trap (JPY billions vs millions)",
         T7_TEXT, "north_america_revenue_usd, europe_revenue_usd, europe_revenue_eur, europe_revenue_gbp, japan_revenue_usd, japan_revenue_jpy_billions, total_revenue_usd, eur_usd_rate, gbp_usd_rate, jpy_usd_rate",
         T7_TRUTH, tolerance=0.01)


# ─────────────────────────────────────────────────────────────
# T8: Debt maturity schedule + effective interest rate
# ─────────────────────────────────────────────────────────────
T8_TEXT = """
NOTE 9 — LONG-TERM DEBT (in millions)

                            Principal    Unamortized     Carrying
                            Amount       Discount/OID    Value
3.250% Notes due 2025       $500.0       $(1.2)          $498.8
4.125% Notes due 2027       $750.0       $(4.8)          $745.2
5.500% Notes due 2030       $1,000.0     $(9.1)          $990.9
6.875% Notes due 2033       $800.0       $(14.3)         $785.7
Total long-term debt        $3,050.0     $(29.4)         $3,020.6
Less: current portion                                    $(498.8)  (1)
Long-term debt, net                                      $2,521.8

Annual maturities of long-term debt (principal only):
2025: $500.0    2026: $—    2027: $750.0    2028: $—
2029: $—        2030: $1,000.0              2031 and thereafter: $800.0

(1) The 3.250% Notes due 2025 are classified as current as they mature within
    12 months of December 31, 2023 (reporting date).

Weighted average interest rate on total debt: 4.89%
"""

T8_TRUTH = {
    "total_principal": 3050.0,
    "total_carrying_value": 3020.6,
    "total_discount": -29.4,           # negative (OID)
    "current_portion": -498.8,         # negative
    "longterm_debt_net": 2521.8,
    "notes_2025_rate_pct": 3.250,
    "notes_2033_carrying": 785.7,
    "maturity_2025": 500.0,
    "maturity_2026": 0,                # TRAP: — means zero
    "maturity_2027": 750.0,
    "maturity_after_2030": 800.0,      # TRAP: "2031 and thereafter"
    "weighted_avg_rate_pct": 4.89,
    "reporting_date_year": 2023,       # from footnote (1)
}
run_test("T8: Debt schedule + OID + current vs long-term + dash-zero + rate extraction",
         T8_TEXT, "total_principal, total_carrying_value, total_discount, current_portion, longterm_debt_net, notes_2025_rate_pct, notes_2033_carrying, maturity_2025, maturity_2026, maturity_2027, maturity_after_2030, weighted_avg_rate_pct, reporting_date_year",
         T8_TRUTH, tolerance=0.05)


# ─────────────────────────────────────────────────────────────
# T9: Effective tax rate reconciliation
# ─────────────────────────────────────────────────────────────
T9_TEXT = """
NOTE 11 — INCOME TAXES

The reconciliation of the U.S. federal statutory tax rate to our effective tax rate:

                                            FY2023      FY2022
U.S. federal statutory rate                 21.0%       21.0%
State and local taxes, net of federal       2.4%        2.1%
Foreign rate differential                   (3.8%)      (4.2%)
R&D tax credits                             (2.1%)      (1.8%)
Stock-based compensation                    (1.4%)      (0.9%)
Non-deductible executive compensation       0.8%        0.7%
GILTI inclusion                             1.9%        2.3%
Valuation allowance change                  4.2%        (0.3%)
Other, net                                  0.3%        0.1%
Effective tax rate                          23.3%       19.0%

Income before taxes: $892.4M (FY2023), $1,041.2M (FY2022)
"""

T9_TRUTH = {
    "statutory_rate_fy2023": 21.0,
    "effective_rate_fy2023": 23.3,
    "effective_rate_fy2022": 19.0,
    "foreign_rate_diff_fy2023": -3.8,   # negative (benefit)
    "rd_credits_fy2023": -2.1,          # negative (benefit)
    "valuation_allowance_fy2023": 4.2,  # positive (expense)
    "valuation_allowance_fy2022": -0.3, # negative (benefit) — TRAP: (0.3%)
    "gilti_fy2023": 1.9,
    "income_before_tax_fy2023": 892.4,
    "income_before_tax_fy2022": 1041.2,
    "tax_expense_fy2023": round(892.4 * 0.233, 1),  # = 207.9 — requires calc
    "rate_change_yoy": round(23.3 - 19.0, 1),       # = 4.3 percentage points
}
run_test("T9: Tax rate reconciliation + negative percentages + derived tax amount",
         T9_TEXT, "statutory_rate_fy2023, effective_rate_fy2023, effective_rate_fy2022, foreign_rate_diff_fy2023, rd_credits_fy2023, valuation_allowance_fy2023, valuation_allowance_fy2022, gilti_fy2023, income_before_tax_fy2023, income_before_tax_fy2022, tax_expense_fy2023, rate_change_yoy",
         T9_TRUTH, tolerance=0.15)


# ─────────────────────────────────────────────────────────────
# T10: Lease obligations (ASC 842) — present value trap
# ─────────────────────────────────────────────────────────────
T10_TEXT = """
NOTE 7 — LEASES (in millions)

Future minimum lease payments under non-cancellable leases as of Dec 31, 2023:

                        Operating Leases    Finance Leases
2024                    $42.8               $12.3
2025                    $39.1               $11.8
2026                    $35.7               $10.2
2027                    $31.2               $8.7
2028                    $26.8               $6.4
2029 and thereafter     $89.4               $15.8
Total undiscounted      $265.0              $65.2
Less: imputed interest  $(38.2)             $(8.4)
Present value of lease  $226.8              $56.8
  liabilities
  Current portion       $(38.1)             $(11.2)
  Non-current portion   $188.7              $45.6

Weighted average remaining lease term: 6.8 years (operating), 5.2 years (finance)
Weighted average discount rate: 4.3% (operating), 3.8% (finance)
"""

T10_TRUTH = {
    "operating_lease_2024": 42.8,
    "finance_lease_2024": 12.3,
    "operating_total_undiscounted": 265.0,
    "finance_total_undiscounted": 65.2,
    "operating_imputed_interest": -38.2,  # negative
    "operating_pv": 226.8,
    "finance_pv": 56.8,
    "total_lease_liability": 226.8 + 56.8,  # = 283.6 — requires calc
    "operating_noncurrent": 188.7,
    "finance_current": -11.2,              # negative (current portion)
    "operating_discount_rate_pct": 4.3,
    "finance_remaining_years": 5.2,
    "operating_after_2028": 89.4,          # TRAP: "2029 and thereafter" label
}
run_test("T10: ASC 842 leases + imputed interest + PV calc + 'thereafter' trap",
         T10_TEXT, "operating_lease_2024, finance_lease_2024, operating_total_undiscounted, finance_total_undiscounted, operating_imputed_interest, operating_pv, finance_pv, total_lease_liability, operating_noncurrent, finance_current, operating_discount_rate_pct, finance_remaining_years, operating_after_2028",
         T10_TRUTH, tolerance=0.05)


# ─────────────────────────────────────────────────────────────
# T11: Stock compensation — vesting schedule + grant types
# ─────────────────────────────────────────────────────────────
T11_TEXT = """
NOTE 13 — STOCK-BASED COMPENSATION (shares in thousands, $ in millions)

RSU activity during FY2023:
                        Shares      Wtd Avg Grant
                                    Date Fair Value
Outstanding Jan 1       8,241       $34.82
Granted                 2,103       $41.67
Vested                  (2,891)     $31.24
Forfeited               (412)       $37.18
Outstanding Dec 31      7,041       $37.94
Expected to vest        6,821       $37.94

Stock options outstanding: None (all options expired or exercised by FY2021)

PSU activity (performance share units):
  Outstanding: 1,240 shares (at target); range 0%–200% of target
  Weighted average fair value: $44.12 per share
  Performance period: Jan 1, 2022 – Dec 31, 2024

Total unrecognized compensation cost: $87.3M
Weighted average recognition period: 2.4 years
FY2023 stock compensation expense: $41.2M (included in operating expenses)
FY2022 stock compensation expense: $38.7M
"""

T11_TRUTH = {
    "rsu_outstanding_start": 8241,
    "rsu_granted": 2103,
    "rsu_vested": -2891,                    # negative (reduction)
    "rsu_forfeited": -412,                  # negative
    "rsu_outstanding_end": 7041,
    "rsu_grant_fair_value": 41.67,
    "rsu_vested_fair_value": 31.24,
    "stock_options_outstanding": 0,         # TRAP: "None"
    "psu_shares_at_target": 1240,
    "psu_max_pct": 200,                     # TRAP: "0%-200%", max is 200
    "psu_fair_value": 44.12,
    "unrecognized_comp_cost": 87.3,
    "recognition_period_years": 2.4,
    "sbc_expense_fy2023": 41.2,
    "sbc_expense_fy2022": 38.7,
}
run_test("T11: RSU/PSU/options activity + None-as-zero + percentage range + multiple grant types",
         T11_TEXT, "rsu_outstanding_start, rsu_granted, rsu_vested, rsu_forfeited, rsu_outstanding_end, rsu_grant_fair_value, rsu_vested_fair_value, stock_options_outstanding, psu_shares_at_target, psu_max_pct, psu_fair_value, unrecognized_comp_cost, recognition_period_years, sbc_expense_fy2023, sbc_expense_fy2022",
         T11_TRUTH, tolerance=0.05)


# ─────────────────────────────────────────────────────────────
# T12: Revenue recognition — deferred vs recognized
# ─────────────────────────────────────────────────────────────
T12_TEXT = """
NOTE 3 — REVENUE (in millions)

Disaggregation of revenue:
                        Recognized      Deferred        Total
                        Point-in-time   Over-time       Contracted
Product sales           $1,842.3        $—              $1,842.3
Service subscriptions   $234.7          $891.2          $1,125.9  (1)
Maintenance contracts   $—              $412.8          $412.8
Licensing               $98.4           $156.3          $254.7
Total                   $2,175.4        $1,460.3        $3,635.7

Deferred revenue balances:
  Current (to be recognized within 12 months)    $687.4
  Non-current                                    $772.9
  Total deferred revenue                        $1,460.3

(1) Service subscription total contracted value includes $312.4M from contracts
    signed in FY2023 but commencing in FY2024 (not yet in deferred revenue balance
    as performance obligation not yet active). Actual deferred revenue from
    subscriptions = $578.8M ($891.2M less $312.4M).

Revenue expected to be recognized from remaining performance obligations:
  Next 12 months: $687.4    13-24 months: $421.3    Thereafter: $351.6
"""

T12_TRUTH = {
    "product_sales_recognized": 1842.3,
    "service_subscriptions_total": 1125.9,
    "service_deferred": 891.2,
    "maintenance_recognized": 0,           # TRAP: — means zero
    "total_recognized": 2175.4,
    "total_deferred_balance": 1460.3,
    "deferred_current": 687.4,
    "deferred_noncurrent": 772.9,
    "subscription_not_yet_active": 312.4,  # TRAP: from footnote (1)
    "subscription_actual_deferred": 578.8, # TRAP: derived in footnote
    "rpb_next_12_months": 687.4,
    "rpb_13_24_months": 421.3,
    "rpb_thereafter": 351.6,
}
run_test("T12: Deferred vs recognized revenue + footnote correction + RPO schedule",
         T12_TEXT, "product_sales_recognized, service_subscriptions_total, service_deferred, maintenance_recognized, total_recognized, total_deferred_balance, deferred_current, deferred_noncurrent, subscription_not_yet_active, subscription_actual_deferred, rpb_next_12_months, rpb_13_24_months, rpb_thereafter",
         T12_TRUTH, tolerance=0.05)


# ─────────────────────────────────────────────────────────────
# T13: Contingent liabilities — probability language trap
# ─────────────────────────────────────────────────────────────
T13_TEXT = """
NOTE 16 — COMMITMENTS AND CONTINGENCIES (in millions)

Legal Proceedings:

Patent Litigation (Case A): The Company is defendant in a patent infringement
suit. Management believes a loss is PROBABLE. The Company has accrued $23.5M
as the best estimate within a range of $15.0M to $45.0M.

Environmental Remediation (Site B): Cleanup costs are REASONABLY POSSIBLE
but not probable. Estimated cost range: $8.2M to $31.7M. No accrual recorded.

Contract Dispute (Case C): A former supplier claims $142.8M in damages.
Management believes the risk of loss is REMOTE. No accrual recorded.
The Company's legal counsel estimates maximum exposure at $28.4M
(discounted settlement value).

Tax Contingency: The Company has recorded an uncertain tax position liability
of $41.2M (net of $12.8M federal benefit). Gross unrecognized tax benefit: $54.0M.

Total accrued contingent liabilities: $64.7M ($23.5M legal + $41.2M tax)
"""

T13_TRUTH = {
    "case_a_accrued": 23.5,
    "case_a_range_low": 15.0,
    "case_a_range_high": 45.0,
    "case_a_probability": "probable",
    "site_b_accrued": 0,               # TRAP: "no accrual recorded"
    "site_b_probability": "reasonably possible",
    "case_c_damages_claimed": 142.8,
    "case_c_accrued": 0,               # TRAP: remote = no accrual
    "case_c_max_exposure": 28.4,       # TRAP: NOT 142.8
    "tax_contingency_net": 41.2,
    "gross_unrecognized_tax": 54.0,
    "federal_tax_benefit": 12.8,       # TRAP: in parenthetical
    "total_accrued": 64.7,
}
run_test("T13: Probability language + accrual vs exposure + tax UTP netting",
         T13_TEXT, "case_a_accrued, case_a_range_low, case_a_range_high, case_a_probability, site_b_accrued, site_b_probability, case_c_damages_claimed, case_c_accrued, case_c_max_exposure, tax_contingency_net, gross_unrecognized_tax, federal_tax_benefit, total_accrued",
         T13_TRUTH, tolerance=0.05)


# ─────────────────────────────────────────────────────────────
# T14: Cash flow — indirect method (many add-backs, working capital)
# ─────────────────────────────────────────────────────────────
T14_TEXT = """
CONSOLIDATED STATEMENTS OF CASH FLOWS (in millions)
Year ended December 31, 2023

OPERATING ACTIVITIES
Net income                                          $218.4
Adjustments to reconcile net income to cash:
  Depreciation and amortization                      67.3
  Stock-based compensation                           41.2
  Deferred income taxes                             (14.8)
  Impairment charges                                 23.5
  Gain on sale of investments                        (8.1)
  Other non-cash items                                3.2
Changes in operating assets and liabilities:
  Accounts receivable                               (42.3)
  Inventories                                        12.8
  Prepaid and other assets                          (18.4)
  Accounts payable                                   31.7
  Accrued liabilities                               (22.1)
  Deferred revenue                                   87.4
Net cash provided by operating activities           $379.8 (1)

INVESTING ACTIVITIES
  Capital expenditures                             (112.4)
  Acquisitions, net of cash acquired               (284.1)
  Purchases of investments                         (891.2)
  Proceeds from sale of investments                 421.8
Net cash used in investing activities             $(865.9)

FINANCING ACTIVITIES
  Repayment of long-term debt                      (200.0)
  Proceeds from stock option exercises               12.3
  Taxes paid on vested RSUs                         (18.7)
  Share repurchases                                (150.0)
  Dividends paid                                    (42.8)
Net cash used in financing activities             $(399.2)

Net decrease in cash                               $(885.3)
Cash at beginning of year                           $923.4
Cash at end of year                                  $38.1

(1) Includes $12.4M of interest paid and $31.8M of income taxes paid,
    classified as operating activities per ASC 230.
"""

T14_TRUTH = {
    "net_income": 218.4,
    "depreciation": 67.3,
    "deferred_taxes": -14.8,            # negative (benefit)
    "gain_on_investments": -8.1,        # negative (add-back reversal)
    "ar_change": -42.3,                 # negative (increase in AR = use of cash)
    "deferred_revenue_change": 87.4,    # positive (increase = source of cash)
    "cfo": 379.8,
    "capex": -112.4,                    # negative
    "acquisitions": -284.1,             # negative
    "cfi": -865.9,
    "share_repurchases": -150.0,        # negative
    "dividends_paid": -42.8,            # negative
    "cff": -399.2,
    "net_cash_change": -885.3,
    "cash_beginning": 923.4,
    "cash_ending": 38.1,
    "interest_paid": 12.4,              # TRAP: from footnote (1)
    "taxes_paid_operating": 31.8,       # TRAP: from footnote (1)
}
run_test("T14: Cash flow indirect method + working capital signs + footnote cash payments",
         T14_TEXT, "net_income, depreciation, deferred_taxes, gain_on_investments, ar_change, deferred_revenue_change, cfo, capex, acquisitions, cfi, share_repurchases, dividends_paid, cff, net_cash_change, cash_beginning, cash_ending, interest_paid, taxes_paid_operating",
         T14_TRUTH, tolerance=0.05)


# ─────────────────────────────────────────────────────────────
# T15: Pension — corridor vs PBO vs fair value confusion
# ─────────────────────────────────────────────────────────────
T15_TEXT = """
NOTE 17 — EMPLOYEE BENEFIT PLANS (in millions)

Defined Benefit Pension Plan — Change in Benefit Obligation:
  PBO at beginning of year                        $1,241.8
  Service cost                                       34.2
  Interest cost                                      62.1
  Actuarial (gain) loss                             (89.3)  (a)
  Benefits paid                                     (71.4)
  PBO at end of year                             $1,177.4

Change in Plan Assets:
  Fair value at beginning of year                $1,089.3
  Actual return on plan assets                      143.7
  Employer contributions                             45.0
  Benefits paid                                     (71.4)
  Fair value at end of year                      $1,206.6

Funded Status (surplus):                           $29.2   (b)

(a) Actuarial gain driven primarily by 50bps increase in discount rate
    from 4.75% to 5.25%. No corridor amortization required as accumulated
    gain is within 10% corridor threshold.
(b) Funded status = Plan assets ($1,206.6M) minus PBO ($1,177.4M) = $29.2M surplus.
    Recognized in balance sheet as non-current asset.

Key assumptions: Discount rate 5.25%, expected return on assets 7.0%,
salary growth rate 3.5%.
"""

T15_TRUTH = {
    "pbo_beginning": 1241.8,
    "service_cost": 34.2,
    "actuarial_gain_loss": -89.3,       # negative = gain
    "pbo_ending": 1177.4,
    "plan_assets_beginning": 1089.3,
    "actual_return": 143.7,
    "plan_assets_ending": 1206.6,
    "funded_status": 29.2,              # positive = surplus
    "discount_rate_pct": 5.25,
    "prior_discount_rate_pct": 4.75,    # TRAP: "from 4.75% to 5.25%"
    "rate_increase_bps": 50,            # TRAP: "50bps"
    "expected_return_pct": 7.0,
    "salary_growth_pct": 3.5,
    "corridor_breach": 0,              # TRAP: explicitly "not required" = 0/false
}
run_test("T15: Pension PBO + funded status + actuarial gains + basis points + corridor",
         T15_TEXT, "pbo_beginning, service_cost, actuarial_gain_loss, pbo_ending, plan_assets_beginning, actual_return, plan_assets_ending, funded_status, discount_rate_pct, prior_discount_rate_pct, rate_increase_bps, expected_return_pct, salary_growth_pct, corridor_breach",
         T15_TRUTH, tolerance=0.05)


print("\n" + "="*65)
print("ALL TESTS COMPLETE")
