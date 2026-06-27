"""
10 тестів на РЕАЛЬНИХ 10-K звітах з SEC EDGAR
Tesla, Amazon, Meta, Nvidia, Alphabet, Netflix, JPMorgan, J&J
"""
import os, json, re
from groq import Groq

client = Groq(api_key=os.environ["OPENAI_API_KEY"])
MODEL = "llama-3.3-70b-versatile"
SCORES = []

def ask(text, fields):
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "Extract financial data from SEC 10-K filings. Return JSON only. All values must be final computed numbers, never expressions. Negative for losses/expenses shown in parentheses. Null if unavailable."},
                {"role": "user", "content": f"Extract from 10-K filing:\n\n{text}\n\nFields: {fields}"}
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        print(f"  [API ERROR]: {str(e)[:150]}")
        return {}

def score(name, result, truth, tol=1.0):
    correct = wrong = 0
    errors = []
    for field, expected in truth.items():
        got = result.get(field, "MISSING")
        if expected is None:
            ok = got is None or got == 0
        elif isinstance(expected, (int, float)) and isinstance(got, (int, float)):
            ok = abs(float(got) - float(expected)) <= tol
        elif isinstance(expected, str):
            ok = str(got).strip().lower() == expected.lower()
        else:
            ok = str(got) == str(expected)
        if ok: correct += 1
        else:
            wrong += 1
            errors.append(f"    {field}: expected={expected}, got={got}")
    pct = correct/(correct+wrong)*100
    status = "OK" if pct==100 else ("PARTIAL" if pct>=70 else "FAIL")
    print(f"\n{'='*60}")
    print(f"{name}")
    print(f"SCORE: {correct}/{correct+wrong} = {pct:.0f}%  [{status}]")
    for e in errors: print(e)
    SCORES.append((name, pct))
    return pct


# ─────────────────────────────────────────────────────────────
# R1: TESLA FY2023 — сегментні доходи + негативний податок
# Пастка: Tesla отримала TAX BENEFIT (від'ємний податок)
# ─────────────────────────────────────────────────────────────
TESLA = """
Tesla, Inc. — Consolidated Statements of Operations ($ in Millions)
12 Months Ended December 31, 2023

Revenues:
  Automotive sales                    $78,509
  Automotive regulatory credits        $1,790
  Automotive leasing                   $2,120
  Total Automotive revenues           $82,419
  Energy generation and storage        $6,035
  Services and other                   $8,319
  Total revenues                      $96,773

Cost of revenues:
  Automotive                          $66,389
  Energy generation and storage        $4,894
  Services and other                   $7,830
  Total cost of revenues              $79,113
Gross profit                          $17,660

Operating expenses:
  Research and development             $3,969
  Selling, general and administrative  $4,800
  Restructuring and other                  $0
  Total operating expenses             $8,769
Income from operations                 $8,891

Interest income                        $1,066
Interest expense                        ($156)
Other income (expense), net              $172
Income before income taxes             $9,973
(Benefit from) provision for income taxes ($5,001)
Net income                            $14,974
Net income attributable to common stockholders $14,997

EPS Basic: $4.73    EPS Diluted: $4.30
Weighted avg shares Basic: 3,174M   Diluted: 3,485M
"""

R1 = ask(TESLA, "total_revenues, automotive_revenues, energy_revenues, services_revenues, gross_profit, operating_income, income_tax_benefit_or_expense, net_income, net_income_to_common, eps_basic, eps_diluted, automotive_sales_only, regulatory_credits")
score("R1: Tesla FY2023 — сегменти + негативний податок", R1, {
    "total_revenues": 96773,
    "automotive_revenues": 82419,
    "energy_revenues": 6035,
    "services_revenues": 8319,
    "gross_profit": 17660,
    "operating_income": 8891,
    "income_tax_benefit_or_expense": -5001,   # ПАСТКА: benefit = negative
    "net_income": 14974,
    "net_income_to_common": 14997,            # ПАСТКА: різниця від net_income
    "eps_basic": 4.73,
    "eps_diluted": 4.30,
    "automotive_sales_only": 78509,           # ПАСТКА: не плутати з total automotive
    "regulatory_credits": 1790,
}, tol=0.01)


# ─────────────────────────────────────────────────────────────
# R2: AMAZON FY2023 — збиток у 2022, product vs service split
# Пастка: FY2022 чистий збиток = від'ємне число
# ─────────────────────────────────────────────────────────────
AMAZON = """
Amazon.com, Inc. — Consolidated Statements of Operations ($ in Millions)
12 Months Ended December 31:

                                2023        2022        2021
Total net sales              $574,785    $513,983    $469,822
  Net product sales          $255,887    $242,901    $241,787
  Net service sales          $318,898    $271,082    $228,035

Operating expenses:
  Cost of sales              $304,739    $288,831    $272,344
  Fulfillment                 $90,619     $84,299     $75,111
  Technology & infrastructure $85,622     $73,213     $56,052
  Sales and marketing         $44,370     $42,238     $32,551
  General and administrative  $11,816     $11,891      $8,823
  Other operating expense        $767      $1,263         $62
  Total operating expenses   $537,933    $501,735    $444,943
Operating income              $36,852     $12,248     $24,879

Interest income                $2,949        $989        $448
Interest expense               ($3,182)    ($2,367)    ($1,809)
Other income (expense), net       $938    ($16,806)    $14,633
Income (loss) before taxes    $37,557     ($5,936)    $38,151
Provision (benefit) for taxes  ($7,120)     $3,217     ($4,791)
Net income (loss)             $30,425     ($2,722)    $33,364

EPS Basic 2023: $2.95   Diluted: $2.90
EPS Basic 2022: ($0.27) Diluted: ($0.27)
"""

R2 = ask(AMAZON, "total_sales_2023, product_sales_2023, service_sales_2023, operating_income_2023, net_income_2023, net_income_2022, net_income_2021, eps_basic_2023, eps_basic_2022, fulfillment_2023, other_income_2022, services_share_pct_2023")
score("R2: Amazon FY2023 — збиток 2022 + product/service split + частка сервісів", R2, {
    "total_sales_2023": 574785,
    "product_sales_2023": 255887,
    "service_sales_2023": 318898,
    "operating_income_2023": 36852,
    "net_income_2023": 30425,
    "net_income_2022": -2722,              # ПАСТКА: збиток = від'ємне
    "net_income_2021": 33364,
    "eps_basic_2023": 2.95,
    "eps_basic_2022": -0.27,              # ПАСТКА: від'ємний EPS
    "fulfillment_2023": 90619,
    "other_income_2022": -16806,          # ПАСТКА: великий збиток
    "services_share_pct_2023": round(318898/574785*100, 1),  # 55.5% — розрахунок
}, tol=0.1)


# ─────────────────────────────────────────────────────────────
# R3: META FY2023 — YoY growth + Reality Labs (збитки)
# ─────────────────────────────────────────────────────────────
META = """
Meta Platforms, Inc. — Consolidated Statements of Income ($ in Millions)
12 Months Ended December 31:

                                    2023        2022        2021
Revenue                          $134,902    $116,609    $117,929
Cost of revenue                   $25,959     $25,249     $22,649
Research and development          $38,483     $35,338     $24,655
Marketing and sales               $12,301     $15,262     $14,043
General and administrative        $11,408     $11,816      $9,829
Total costs and expenses          $88,151     $87,665     $71,176
Income from operations            $46,751     $28,944     $46,753
Interest and other income (exp)      $677       ($125)       $531
Income before income taxes        $47,428     $28,819     $47,284
Provision for income taxes         $8,330      $5,619      $7,914
Net income                        $39,098     $23,200     $39,370

EPS Basic: $15.19 / Diluted: $14.87
Weighted avg shares: Basic 2,574M / Diluted 2,629M

Note: Revenue in 2022 DECLINED year-over-year from 2021 ($117,929M to $116,609M).
Operating margin FY2023 = 46,751 / 134,902 = 34.7%
"""

R3 = ask(META, "revenue_2023, revenue_2022, revenue_2021, operating_income_2023, operating_income_2022, net_income_2023, net_income_2022, rd_2023, marketing_2023, eps_diluted_2023, revenue_yoy_change_2022, operating_margin_2023_pct")
score("R3: Meta FY2023 — revenue decline 2022 + margins", R3, {
    "revenue_2023": 134902,
    "revenue_2022": 116609,
    "revenue_2021": 117929,
    "operating_income_2023": 46751,
    "operating_income_2022": 28944,
    "net_income_2023": 39098,
    "net_income_2022": 23200,
    "rd_2023": 38483,
    "marketing_2023": 12301,
    "eps_diluted_2023": 14.87,
    "revenue_yoy_change_2022": round(116609 - 117929, 0),  # = -1320 decline
    "operating_margin_2023_pct": 34.7,
}, tol=0.15)


# ─────────────────────────────────────────────────────────────
# R4: NVIDIA FY2024 — нестандартний фіскальний рік (Jan 28, 2024)
# Пастка: fiscal year ends in JANUARY, not December
# ─────────────────────────────────────────────────────────────
NVIDIA = """
NVIDIA Corporation — Consolidated Statements of Income ($ in Millions)
Fiscal Years Ended:

                            Jan 28, 2024    Jan 29, 2023    Jan 30, 2022
Revenue                        $60,922         $26,974         $26,914
Cost of revenue                $16,621         $11,618          $9,439
Gross profit                   $44,301         $15,356         $17,475

Operating expenses:
  Research and development      $8,675          $7,339          $5,268
  Sales, general & admin        $2,654          $2,440          $2,166
  Acquisition termination cost      $0          $1,353              $0
  Total operating expenses     $11,329         $11,132          $7,434
Operating income               $32,972          $4,224         $10,041

Interest income                   $866            $267             $29
Interest expense                 ($257)          ($262)          ($236)
Other, net                        $237            ($48)           $107
Income before income tax       $33,818          $4,181          $9,941
Income tax expense (benefit)    $4,058           ($187)           $189
Net income                     $29,760          $4,368          $9,752

EPS Basic: $12.05  Diluted: $11.93
"""

R4 = ask(NVIDIA, "revenue_fy2024, revenue_fy2023, gross_profit_fy2024, operating_income_fy2024, acquisition_termination_fy2023, net_income_fy2024, net_income_fy2023, income_tax_fy2024, income_tax_fy2023, eps_diluted_fy2024, gross_margin_pct_fy2024, fiscal_year_end_date_fy2024, revenue_growth_pct")
score("R4: Nvidia FY2024 — нестандартний фіск.рік Jan + acquisition cost", R4, {
    "revenue_fy2024": 60922,
    "revenue_fy2023": 26974,
    "gross_profit_fy2024": 44301,
    "operating_income_fy2024": 32972,
    "acquisition_termination_fy2023": 1353,    # ПАСТКА: тільки в FY2023, не 2024
    "net_income_fy2024": 29760,
    "net_income_fy2023": 4368,
    "income_tax_fy2024": 4058,
    "income_tax_fy2023": -187,                 # ПАСТКА: benefit = від'ємне
    "eps_diluted_fy2024": 11.93,
    "gross_margin_pct_fy2024": round(44301/60922*100, 1),  # 72.7%
    "fiscal_year_end_date_fy2024": "2024-01-28",  # ПАСТКА: не Dec 31!
    "revenue_growth_pct": round((60922-26974)/26974*100, 1),  # 125.8%
}, tol=0.15)


# ─────────────────────────────────────────────────────────────
# R5: ALPHABET FY2023 — Other income swing (12B→-3.5B→1.4B)
# ─────────────────────────────────────────────────────────────
ALPHABET = """
Alphabet Inc. — Consolidated Statements of Income ($ in Millions)
12 Months Ended December 31:

                                2023        2022        2021
Revenues                     $307,394    $282,836    $257,637
Cost of revenues             $133,332    $126,203    $110,939
Research and development      $45,427     $39,500     $31,562
Sales and marketing           $27,917     $26,567     $22,912
General and administrative    $16,425     $15,724     $13,510
Total costs and expenses     $223,101    $207,994    $178,923
Income from operations        $84,293     $74,842     $78,714

Other income (expense), net    $1,424     ($3,514)    $12,020
Total income before taxes     $85,717     $71,328     $90,734
Provision for income taxes    $11,922     $11,356     $14,701
Net income                    $73,795     $59,972     $76,033

EPS Basic: $5.84   Diluted: $5.80
"""

R5 = ask(ALPHABET, "revenue_2023, revenue_2022, operating_income_2023, other_income_2023, other_income_2022, other_income_2021, net_income_2023, net_income_2022, income_tax_2023, eps_diluted_2023, other_income_swing_2022_to_2021, operating_margin_pct_2023")
score("R5: Alphabet FY2023 — other income великі коливання між роками", R5, {
    "revenue_2023": 307394,
    "revenue_2022": 282836,
    "operating_income_2023": 84293,
    "other_income_2023": 1424,
    "other_income_2022": -3514,          # ПАСТКА: від'ємне
    "other_income_2021": 12020,
    "net_income_2023": 73795,
    "net_income_2022": 59972,
    "income_tax_2023": 11922,
    "eps_diluted_2023": 5.80,
    "other_income_swing_2022_to_2021": round(-3514 - 12020, 0),  # = -15534
    "operating_margin_pct_2023": round(84293/307394*100, 1),  # 27.4%
}, tol=0.15)


# ─────────────────────────────────────────────────────────────
# R6: NETFLIX FY2025 — CRITICAL TRAP: значення в ТИСЯЧАХ, не мільйонах!
# EPS теж в тисячах shares але в доларах per share
# ─────────────────────────────────────────────────────────────
NETFLIX = """
Netflix, Inc. — Consolidated Statements of Operations
NOTE: All dollar amounts in THOUSANDS. Shares in Thousands.
12 Months Ended December 31:

                                    2025            2024            2023
Revenues                       $45,183,036     $39,000,966     $33,723,297
Cost of revenues               $23,275,329     $21,038,464     $19,715,368
Sales and marketing             $3,301,306      $2,917,554      $2,657,883
Technology and development      $3,391,390      $2,925,295      $2,675,758
General and administrative      $1,888,408      $1,702,039      $1,720,285
Operating income               $13,326,603     $10,417,614      $6,954,003
Interest expense                 ($776,510)      ($718,733)       ($699,826)
Interest and other income          $172,459        $266,776        ($48,772)
Income before income taxes     $12,722,552      $9,965,657      $6,205,405
Provision for income taxes      ($1,741,351)    ($1,254,026)      ($797,415)
Net income                     $10,981,201      $8,711,631      $5,407,990

EPS Basic ($/share): $2.58 / $2.03 / $1.22
EPS Diluted ($/share): $2.53 / $1.98 / $1.20
Shares Basic (thousands): 4,249,512 / 4,295,191 / 4,415,712
"""

R6 = ask(NETFLIX, "revenue_2025_thousands, revenue_2024_thousands, operating_income_2025_thousands, net_income_2025_thousands, net_income_2025_millions, eps_basic_2025, eps_diluted_2025, interest_expense_2025_thousands, income_tax_2025_thousands, revenue_growth_2025_pct, shares_basic_2025_thousands")
score("R6: Netflix FY2025 — ПАСТКА: значення в ТИСЯЧАХ не мільйонах", R6, {
    "revenue_2025_thousands": 45183036,      # в тисячах = $45.18B
    "revenue_2024_thousands": 39000966,
    "operating_income_2025_thousands": 13326603,
    "net_income_2025_thousands": 10981201,
    "net_income_2025_millions": 10981.2,     # ПАСТКА: конвертація
    "eps_basic_2025": 2.58,                  # EPS в доларах (не тисячах!)
    "eps_diluted_2025": 2.53,
    "interest_expense_2025_thousands": -776510,  # від'ємне
    "income_tax_2025_thousands": -1741351,       # від'ємне (expense)
    "revenue_growth_2025_pct": round((45183036-39000966)/39000966*100, 1),  # 15.8%
    "shares_basic_2025_thousands": 4249512,
}, tol=0.5)


# ─────────────────────────────────────────────────────────────
# R7: JPMORGAN FY2025 — банківська структура (interest + noninterest)
# Пастка: investment securities LOSSES (від'ємне у доходах!)
# ─────────────────────────────────────────────────────────────
JPM = """
JPMorgan Chase & Co. — Consolidated Statements of Income ($ in Millions)
12 Months Ended December 31:

                                    2025        2024        2023
Noninterest revenue:
  Investment banking fees           $9,615      $8,910      $6,519
  Principal transactions           $27,212     $24,787     $24,460
  Lending and deposit-related fees  $9,093      $7,606      $7,413
  Asset management fees            $20,327     $17,801     $15,220
  Commissions and other fees        $8,539      $7,530      $6,836
  Investment securities losses        ($57)    ($1,021)    ($3,180)
  Mortgage fees and related income  $1,381      $1,401      $1,176
  Card income                       $4,720      $5,497      $4,784
  Other income                      $6,174     $12,462      $5,609
  Total noninterest revenue        $87,004     $84,973     $68,837

Interest income                   $193,341    $193,933    $170,588
Interest expense                  ($97,898)  ($101,350)   ($81,321)
Net interest income                $95,443     $92,583     $89,267
Total net revenue                 $182,447    $177,556    $158,104

Provision for credit losses        $14,212     $10,678      $9,320
Total noninterest expense          $95,640     $91,797     $87,172
Income before income tax           $72,595     $75,081     $61,612
Income tax expense                 $15,547     $16,610     $12,060
Net income                        $57,048     $58,471     $49,552

EPS Basic 2025: $20.05   Diluted: $20.02
"""

R7 = ask(JPM, "total_revenue_2025, net_interest_income_2025, noninterest_revenue_2025, investment_banking_fees_2025, securities_losses_2025, net_income_2025, net_income_2024, income_tax_2025, provision_credit_losses_2025, eps_diluted_2025, net_income_decline_2025, interest_income_2025, interest_expense_2025")
score("R7: JPMorgan FY2025 — банк: securities losses в доходах + NII структура", R7, {
    "total_revenue_2025": 182447,
    "net_interest_income_2025": 95443,
    "noninterest_revenue_2025": 87004,
    "investment_banking_fees_2025": 9615,
    "securities_losses_2025": -57,          # ПАСТКА: від'ємне у розділі доходів
    "net_income_2025": 57048,
    "net_income_2024": 58471,
    "income_tax_2025": 15547,
    "provision_credit_losses_2025": 14212,
    "eps_diluted_2025": 20.02,
    "net_income_decline_2025": round(57048 - 58471, 0),  # = -1423
    "interest_income_2025": 193341,
    "interest_expense_2025": -97898,        # ПАСТКА: від'ємне
}, tol=1.0)


# ─────────────────────────────────────────────────────────────
# R8: J&J FY2025 — Balance Sheet з вбудованими allowances
# Пастка: "less allowances $183 (2024, $167)" у назві рядка
# ─────────────────────────────────────────────────────────────
JNJ = """
Johnson & Johnson — Consolidated Balance Sheets ($ in Millions)
                                            Dec 28, 2025    Dec 29, 2024
ASSETS
Current assets:
  Cash and cash equivalents                    $19,709         $24,105
  Marketable securities                            $393            $417
  Accounts receivable, trade, less
    allowances of $183 (2024: $167)             $17,178         $14,842
  Inventories                                   $14,191         $12,444
  Prepaid expenses and other receivables         $4,153          $4,085
  Total current assets                          $55,624         $55,893

Non-current assets:
  Property, plant and equipment, net            $23,169         $20,518
  Intangible assets, net                        $50,403         $37,618
  Goodwill                                      $48,772         $44,200
  Deferred taxes on income                       $6,874         $10,461
  Other assets                                  $14,368         $11,414
  Total assets                                 $199,210        $180,104

LIABILITIES
  Loans and notes payable (current)             $8,495          $5,983
  Accounts payable                              $11,991         $10,311
  Accrued liabilities                            $8,594          $8,549
  Accrued rebates, returns and promotions       $19,124         $17,580
  Total current liabilities                     $54,126         $50,321
  Long-term debt                                $39,438         $30,651
  Total liabilities                            $117,666        $108,614

SHAREHOLDERS' EQUITY
  Total shareholders' equity                    $81,544         $71,490
  Total liabilities and equity                 $199,210        $180,104
"""

R8 = ask(JNJ, "cash_2025, total_current_assets_2025, accounts_receivable_net_2025, ar_allowance_2025, ar_allowance_2024, goodwill_2025, goodwill_2024, intangibles_net_2025, total_assets_2025, total_assets_2024, long_term_debt_2025, shareholders_equity_2025, goodwill_increase, total_assets_increase")
score("R8: J&J FY2025 — allowances в описі рядка + cross-year balance sheet", R8, {
    "cash_2025": 19709,
    "total_current_assets_2025": 55624,
    "accounts_receivable_net_2025": 17178,
    "ar_allowance_2025": 183,               # ПАСТКА: вбудовано в назву рядка
    "ar_allowance_2024": 167,               # ПАСТКА: в дужках "(2024: $167)"
    "goodwill_2025": 48772,
    "goodwill_2024": 44200,
    "intangibles_net_2025": 50403,
    "total_assets_2025": 199210,
    "total_assets_2024": 180104,
    "long_term_debt_2025": 39438,
    "shareholders_equity_2025": 81544,
    "goodwill_increase": 48772 - 44200,     # = 4572 — розрахунок
    "total_assets_increase": 199210 - 180104,  # = 19106 — розрахунок
}, tol=1.0)


# ─────────────────────────────────────────────────────────────
# R9: CROSS-COMPANY — порівняти gross margins 5 компаній
# Пастка: різні назви (Cost of revenues vs Cost of sales)
# ─────────────────────────────────────────────────────────────
CROSS = """
Gross Profit Comparison FY2023/FY2024 ($ in Millions unless noted):

TESLA (FY2023, Dec 31):
  Total revenues: $96,773M
  Total cost of revenues: $79,113M
  Gross profit: $17,660M

AMAZON (FY2023, Dec 31):
  Total net sales: $574,785M
  Cost of sales: $304,739M
  Gross profit = Total net sales minus Cost of sales only

META (FY2023, Dec 31):
  Revenue: $134,902M
  Cost of revenue: $25,959M
  Gross profit: $108,943M

NVIDIA (FY2024, Jan 28, 2024):
  Revenue: $60,922M
  Cost of revenue: $16,621M
  Gross profit: $44,301M

ALPHABET (FY2023, Dec 31):
  Revenues: $307,394M
  Cost of revenues: $133,332M
  Gross profit: $174,062M
"""

R9 = ask(CROSS, "tesla_gross_margin_pct, amazon_gross_profit, amazon_gross_margin_pct, meta_gross_margin_pct, nvidia_gross_margin_pct, alphabet_gross_margin_pct, highest_gross_margin_company, lowest_gross_margin_company")
score("R9: Cross-company — gross margins 5 компаній + визначити найвищу/найнижчу", R9, {
    "tesla_gross_margin_pct": round(17660/96773*100, 1),     # 18.2%
    "amazon_gross_profit": 574785 - 304739,                  # 270046 (cost of sales only)
    "amazon_gross_margin_pct": round((574785-304739)/574785*100, 1),  # 47.0%
    "meta_gross_margin_pct": round(108943/134902*100, 1),    # 80.8%
    "nvidia_gross_margin_pct": round(44301/60922*100, 1),    # 72.7%
    "alphabet_gross_margin_pct": round(174062/307394*100, 1), # 56.6%
    "highest_gross_margin_company": "meta",
    "lowest_gross_margin_company": "tesla",
}, tol=0.2)


# ─────────────────────────────────────────────────────────────
# R10: NVIDIA vs TESLA — YoY revenue growth + absolute numbers
# Пастка: Nvidia fiscal year ≠ calendar year
# ─────────────────────────────────────────────────────────────
COMP2 = """
Revenue Comparison:

NVIDIA Corporation:
  FY2022 (ended Jan 30, 2022): Revenue $26,914M
  FY2023 (ended Jan 29, 2023): Revenue $26,974M
  FY2024 (ended Jan 28, 2024): Revenue $60,922M

  Note: NVIDIA fiscal year ends in late January.
  FY2024 covers Feb 2023 – Jan 2024.
  FY2024 net income: $29,760M
  FY2023 net income: $4,368M

TESLA, INC.:
  CY2021 (ended Dec 31, 2021): Revenue $53,823M
  CY2022 (ended Dec 31, 2022): Revenue $81,462M
  CY2023 (ended Dec 31, 2023): Revenue $96,773M

  CY2023 net income: $14,974M
  CY2022 net income: $12,587M
  CY2021 net income: $5,644M
"""

R10 = ask(COMP2, "nvidia_revenue_fy2024, nvidia_revenue_fy2023, nvidia_revenue_growth_pct, nvidia_net_income_fy2024, tesla_revenue_cy2023, tesla_revenue_cy2022, tesla_revenue_growth_pct_cy2023, tesla_net_income_cy2023, nvidia_fiscal_year_end_month, which_company_higher_revenue_fy2024_cy2023, nvidia_net_income_growth_pct")
score("R10: Nvidia vs Tesla — нестандартний фіск.рік + порівняння між компаніями", R10, {
    "nvidia_revenue_fy2024": 60922,
    "nvidia_revenue_fy2023": 26974,
    "nvidia_revenue_growth_pct": round((60922-26974)/26974*100, 1),  # 125.8%
    "nvidia_net_income_fy2024": 29760,
    "tesla_revenue_cy2023": 96773,
    "tesla_revenue_cy2022": 81462,
    "tesla_revenue_growth_pct_cy2023": round((96773-81462)/81462*100, 1),  # 18.8%
    "tesla_net_income_cy2023": 14974,
    "nvidia_fiscal_year_end_month": "january",   # ПАСТКА: не December
    "which_company_higher_revenue_fy2024_cy2023": "tesla",  # 96B > 61B
    "nvidia_net_income_growth_pct": round((29760-4368)/4368*100, 1),  # 581.5%
}, tol=0.2)


# ─────────────────────────────────────────────────────────────
# ПІДСУМОК
# ─────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("SUMMARY — REAL 10-K TESTS")
print("="*60)
total_correct = sum(s for _, s in SCORES)
for name, s in SCORES:
    bar = "█" * int(s/10) + "░" * (10 - int(s/10))
    status = "OK" if s==100 else ("PARTIAL" if s>=70 else "FAIL")
    print(f"  {bar} {s:5.1f}%  {name[:50]}")
avg = total_correct / len(SCORES)
print(f"\nAVERAGE: {avg:.1f}%  ({len([s for _,s in SCORES if s==100])} perfect / {len(SCORES)} total)")
