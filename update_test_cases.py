"""
Оновлює test_cases.jsonl з актуальними expected_verdict
на основі поточних ринкових даних та threshold логіки агента.
"""
import json
import re
import yfinance as yf

THRESHOLDS = {
    "conservative": {"max_pe": 25, "max_beta": 1.0},
    "moderate":     {"max_pe": 35, "max_beta": 1.4},
    "aggressive":   {"max_pe": 60, "max_beta": 2.0},
}

def extract_risk(text: str) -> str:
    t = text.lower()
    if "conserv" in t: return "conservative"
    if "aggress" in t: return "aggressive"
    return "moderate"

def get_verdict(ticker: str, risk_profile: str) -> tuple[str, str]:
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception as e:
        return "UNKNOWN", f"fetch error: {e}"

    thr = THRESHOLDS.get(risk_profile, THRESHOLDS["moderate"])
    pe = info.get("trailingPE")
    beta = info.get("beta")
    margin = info.get("profitMargins")

    rejects = []
    if pe is not None and pe > thr["max_pe"]:
        rejects.append(f"P/E {pe:.1f}x > {thr['max_pe']}x")
    if beta is not None and beta > thr["max_beta"]:
        rejects.append(f"Beta {beta:.2f} > {thr['max_beta']}")
    if margin is not None and margin < 0:
        rejects.append(f"Negative margin {margin*100:.1f}%")

    verdict = "REJECTED" if rejects else "APPROVED"
    reason = "; ".join(rejects) if rejects else f"P/E {pe:.1f}x OK, Beta {beta:.2f} OK"
    return verdict, reason

TEST_CASES_INPUT = [
    {"ticker": "AAPL",  "input": "Analyse AAPL for a conservative investor. Provide a full Due Diligence report."},
    {"ticker": "TSLA",  "input": "Analyse TSLA for a conservative investor. Provide a full Due Diligence report."},
    {"ticker": "MSFT",  "input": "Analyse MSFT for a moderate risk investor. Provide a full Due Diligence report."},
    {"ticker": "NVDA",  "input": "Analyse NVDA for a conservative investor. Provide a full Due Diligence report."},
    {"ticker": "JNJ",   "input": "Analyse JNJ for a conservative investor. Provide a full Due Diligence report."},
    {"ticker": "GME",   "input": "Analyse GME for a conservative investor. Provide a full Due Diligence report."},
    {"ticker": "GOOGL", "input": "Analyse GOOGL for a moderate investor. Provide a full Due Diligence report."},
    {"ticker": "AMZN",  "input": "Analyse AMZN for an aggressive investor. Provide a full Due Diligence report."},
    {"ticker": "META",  "input": "Analyse META for a moderate investor. Provide a full Due Diligence report."},
    {"ticker": "RIVN",  "input": "Analyse RIVN for a conservative investor. Provide a full Due Diligence report."},
    {"ticker": "PLTR",  "input": "Analyse PLTR for a conservative investor. Provide a full Due Diligence report."},
    {"ticker": "KO",    "input": "Analyse KO (Coca-Cola) for a conservative investor. Provide a full Due Diligence report."},
    {"ticker": "AMD",   "input": "Analyse AMD for an aggressive investor. Provide a full Due Diligence report."},
    {"ticker": "INTC",  "input": "Analyse INTC for a moderate investor. Provide a full Due Diligence report."},
    {"ticker": "SPY",   "input": "Analyse SPY (S&P 500 ETF) for a conservative investor. Provide a full Due Diligence report."},
    {"ticker": "AAPL",  "input": "What is the Kelly Criterion position size for AAPL if my win rate is 60% and payout ratio is 1.5?"},
    {"ticker": "NVDA",  "input": "Analyse NVDA for an aggressive investor. Provide a full Due Diligence report."},
    {"ticker": "BRK-B", "input": "Analyse BRK-B for a conservative investor. Provide a full Due Diligence report."},
    {"ticker": "COIN",  "input": "Analyse COIN for a conservative investor. Provide a full Due Diligence report."},
    {"ticker": "MSFT",  "input": "Analyse MSFT for a conservative investor. Is it suitable?"},
]

print("Fetching current market data and computing verdicts...")
print(f"{'Ticker':8} {'Profile':12} {'Verdict':10} Reason")
print("-" * 65)

updated = []
for tc in TEST_CASES_INPUT:
    ticker = tc["ticker"]
    inp = tc["input"]

    # Kelly test — no verdict
    if "kelly" in inp.lower():
        updated.append({"ticker": ticker, "input": inp, "expected_verdict": None})
        print(f"{'AAPL':8} {'kelly':12} {'N/A':10} open-ended")
        continue

    risk = extract_risk(inp)
    verdict, reason = get_verdict(ticker, risk)
    updated.append({"ticker": ticker, "input": inp, "expected_verdict": verdict})
    print(f"{ticker:8} {risk:12} {verdict:10} {reason}")

# Save updated test cases
with open("pipeline/test_cases.jsonl", "w", encoding="utf-8") as f:
    for tc in updated:
        f.write(json.dumps(tc, ensure_ascii=False) + "\n")

# Also update benchmark.py TEST_CASES list
print("\nDone! Updated pipeline/test_cases.jsonl")
print("\nSummary:")
verdicts = [t["expected_verdict"] for t in updated if t["expected_verdict"]]
print(f"  APPROVED: {verdicts.count('APPROVED')}")
print(f"  REJECTED: {verdicts.count('REJECTED')}")
print(f"  N/A:      {sum(1 for t in updated if t['expected_verdict'] is None)}")
