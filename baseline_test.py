"""
Baseline тест: чи може швидка LLM (Llama 3.3 70B) надійно витягувати
фінансові дані з реального фрагменту Apple 10-K (FY2024)?
"""

import os, json
from groq import Groq

client = Groq(api_key=os.environ["OPENAI_API_KEY"])  # Groq key stored as OPENAI_API_KEY

# === РЕАЛЬНИЙ ФРАГМЕНТ Apple 10-K FY2024, R12.htm ===
# Таблиця "Cash, Cash Equivalents and Marketable Securities" ($ in millions)
# Навмисно залишаємо HTML-ентіті і форматування як у реальному звіті

RAW_TEXT = """
Financial Instruments – Cash, Cash Equivalents and Marketable Securities
The following tables show the Company's cash, cash equivalents and marketable securities
by significant investment category as of September 28, 2024 and September 30, 2023 (in millions):

2024
                              Adjusted Cost  Unrealized Gains  Unrealized Losses  Fair Value  Cash and Cash Equiv.  Current Mkt Sec.  Non-Current Mkt Sec.
Cash                          $27,199        $—                $—                 $27,199     $27,199               $—                $—
Level 1:
  Money market funds          $778           $—                $—                 $778        $778                  $—                $—
  Mutual funds                $515           $105              $(3)               $617        $—                    $617              $—
  Subtotal Level 1            $1,293         $105              $(3)               $1,395      $778                  $617              $—

Level 2 (1):
  U.S. Treasury securities    $16,150        $45               $(516)             $15,679     $212                  $4,087            $11,380
  U.S. agency securities      $5,431         $—                $(272)             $5,159      $155                  $703              $4,301
  Non-U.S. gov. securities    $17,959        $93               $(484)             $17,568     $1,158                $10,810           $5,600
  Certificates of deposit     $873           $—                $—                 $873        $387                  $478              $8
  Commercial paper            $1,066         $—                $—                 $1,066      $28                   $1,038            $—
  Corporate debt securities   $65,622        $270              $(1,953)           $63,939     $26                   $16,027           $47,886
  Municipal securities        $412           $—                $(7)               $405        $—                    $190              $215
  Mortgage- and asset-backed  $10,374        $3                $(327)             $10,050     $—                    $—                $10,050
  Subtotal Level 2            $117,887       $411              $(3,559)           $114,739    $1,966                $33,333           $79,440

Total (2)                     $146,379       $516              $(3,562)           $143,333    $29,943               $33,950           $79,440

(1) The valuation of Level 2 securities is based on matrix pricing using prices of similar securities.
(2) As of September 28, 2024, the Company's total cash, cash equivalents and marketable securities
    was $153,276 million, consisting of the $143,333 million shown above and $9,943 million
    of restricted cash and cash equivalents.
"""

# === GROUND TRUTH — що модель ПОВИННА витягнути ===
GROUND_TRUTH = {
    "reporting_date": "2024-09-28",
    "currency": "USD millions",
    "cash_adjusted_cost": 27199,
    "corporate_debt_fair_value": 63939,
    "corporate_debt_unrealized_losses": -1953,
    "total_fair_value": 143333,
    "level2_subtotal_fair_value": 114739,
    "total_non_current_marketable_securities": 79440,
    "total_with_restricted_cash": 153276,  # ПАСТКА: є у виносці (2), не в таблиці!
    "mutual_funds_unrealized_gains": 105,
    "us_treasury_current_mkt_sec": 4087,
}

# === ПРОМПТ ДЛЯ МОДЕЛІ ===
SCHEMA = {
    "type": "object",
    "properties": {
        "reporting_date": {"type": "string", "description": "Fiscal year end date (YYYY-MM-DD)"},
        "currency": {"type": "string"},
        "cash_adjusted_cost": {"type": "number", "description": "Cash adjusted cost in millions"},
        "corporate_debt_fair_value": {"type": "number", "description": "Corporate debt securities fair value"},
        "corporate_debt_unrealized_losses": {"type": "number", "description": "Corporate debt unrealized losses (negative number)"},
        "total_fair_value": {"type": "number", "description": "Total fair value of all investments"},
        "level2_subtotal_fair_value": {"type": "number", "description": "Level 2 subtotal fair value"},
        "total_non_current_marketable_securities": {"type": "number", "description": "Total non-current marketable securities"},
        "total_with_restricted_cash": {"type": "number", "description": "Total cash including restricted cash (from footnote 2)"},
        "mutual_funds_unrealized_gains": {"type": "number", "description": "Mutual funds unrealized gains"},
        "us_treasury_current_mkt_sec": {"type": "number", "description": "U.S. Treasury current marketable securities"},
    },
    "required": list(GROUND_TRUTH.keys())
}

# === ЗАПУСКАЄМО МОДЕЛЬ ===
print("=" * 60)
print("TEST: Llama-3.3-70b-versatile on Apple 10-K FY2024")
print("=" * 60)

response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[
        {
            "role": "system",
            "content": (
                "You are a financial data extractor. Extract the requested fields "
                "from the provided 10-K filing text. Return ONLY valid JSON matching "
                "the schema. All monetary values should be numbers in millions (as shown). "
                "Losses/negative values should be negative numbers."
            )
        },
        {
            "role": "user",
            "content": f"Extract financial data from this Apple 10-K section:\n\n{RAW_TEXT}\n\nReturn JSON with these fields: {list(GROUND_TRUTH.keys())}"
        }
    ],
    response_format={"type": "json_object"},
    temperature=0,
)

raw_output = response.choices[0].message.content
print(f"\nModel returned:\n{raw_output}\n")

# === АНАЛІЗ РЕЗУЛЬТАТІВ ===
try:
    result = json.loads(raw_output)
except json.JSONDecodeError as e:
    print(f"ПОМИЛКА JSON: {e}")
    exit(1)

print("=" * 60)
print("COMPARISON vs GROUND TRUTH:")
print("=" * 60)
print(f"{'Field':<45} {'Expected':>15} {'Got':>15} {'Status'}")
print("-" * 95)

correct = 0
wrong = 0
missing = 0

for field, expected in GROUND_TRUTH.items():
    got = result.get(field, "MISSING")
    if got == "MISSING":
        status = "MISSING"
        missing += 1
    elif isinstance(expected, (int, float)) and isinstance(got, (int, float)):
        if abs(float(got) - float(expected)) < 0.01:
            status = "OK"
            correct += 1
        else:
            status = f"WRONG (x{float(got)/float(expected):.3f})" if expected != 0 else "WRONG"
            wrong += 1
    elif str(got) == str(expected):
        status = "OK"
        correct += 1
    else:
        status = "WRONG"
        wrong += 1

    print(f"{field:<45} {str(expected):>15} {str(got):>15} {status}")

print("-" * 95)
total = correct + wrong + missing
accuracy = correct / total * 100
print(f"\nRESULT: {correct}/{total} correct -- {accuracy:.0f}% accuracy")
print(f"Correct: {correct}, Wrong: {wrong}, Missing: {missing}")

if accuracy >= 95:
    print("\n[!] CONCLUSION: Model handles this well. Narrow niche.")
elif accuracy >= 70:
    print("\n[+] CONCLUSION: Has errors -- market exists! Fine-tuning makes sense.")
else:
    print("\n[!!] CONCLUSION: Serious errors. Strong differentiation confirmed.")
