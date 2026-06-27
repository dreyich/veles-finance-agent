"""
Veles Finance Agent — Benchmark vs Fine-tune v5 (94.3% baseline)
Runs all 20 test cases against the local Ollama agent and saves results.
"""
import json
import re
import time
import requests
from datetime import datetime

API_URL = "http://localhost:3002/ask"
RESULTS_FILE = "benchmark_results.json"
REPORT_FILE = "benchmark_report.txt"

# Load test cases dynamically from file (updated with current market verdicts)
def _load_test_cases():
    path = "pipeline/test_cases.jsonl"
    try:
        cases = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    cases.append(json.loads(line))
        return cases
    except FileNotFoundError:
        print(f"Warning: {path} not found, using hardcoded cases")
        return []

TEST_CASES = _load_test_cases()


def extract_verdict(text: str) -> str | None:
    """Extract APPROVED/REJECTED from agent response."""
    text_upper = text.upper()
    # Look for explicit verdict words
    if re.search(r'\bAPPROVED\b', text_upper):
        return "APPROVED"
    if re.search(r'\bREJECTED\b', text_upper):
        return "REJECTED"
    # Fallback: look for strong sentiment
    if any(w in text_upper for w in ["SUITABLE", "RECOMMENDED", "BUY", "GOOD FIT"]):
        return "APPROVED"
    if any(w in text_upper for w in ["NOT SUITABLE", "TOO RISKY", "AVOID", "DO NOT"]):
        return "REJECTED"
    return None


def run_test(test: dict, idx: int) -> dict:
    ticker = test["ticker"]
    user_input = test["input"]
    expected = test["expected_verdict"]

    print(f"[{idx:02d}/20] {ticker:6s} | expected={str(expected):8s} | ", end="", flush=True)

    start = time.time()
    try:
        resp = requests.post(API_URL, json={"message": user_input}, timeout=180)
        elapsed = time.time() - start

        if resp.status_code == 200:
            data = resp.json()
            # New API returns structured data with "verdict" field
            got_verdict = data.get("verdict") or extract_verdict(data.get("response", "") or data.get("analysis", ""))

            if expected is None:
                response_text = data.get("response") or data.get("analysis") or str(data)
                passed = len(response_text) > 20
                status = "PASS (no verdict needed)" if passed else "FAIL (empty)"
            else:
                passed = (got_verdict == expected)
                status = f"{'PASS' if passed else 'FAIL'} (got={got_verdict})"

            response_preview = (data.get("analysis") or data.get("response") or str(data))[:300]
            print(f"{elapsed:.1f}s | {status}")
            return {
                "idx": idx,
                "ticker": ticker,
                "expected": expected,
                "got": got_verdict,
                "passed": passed,
                "time_s": round(elapsed, 1),
                "response_preview": response_preview,
                "error": None,
            }
        else:
            print(f"HTTP {resp.status_code}")
            return {"idx": idx, "ticker": ticker, "expected": expected, "got": None,
                    "passed": False, "time_s": round(time.time()-start, 1),
                    "response_preview": "", "error": f"HTTP {resp.status_code}"}

    except Exception as e:
        elapsed = time.time() - start
        print(f"ERROR: {e}")
        return {"idx": idx, "ticker": ticker, "expected": expected, "got": None,
                "passed": False, "time_s": round(elapsed, 1), "response_preview": "", "error": str(e)}


def main():
    print("=" * 65)
    print("  VELES FINANCE AGENT — BENCHMARK")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Baseline: Fine-tune v5 = 94.3%")
    print("=" * 65)

    results = []
    total_start = time.time()

    for i, test in enumerate(TEST_CASES, 1):
        result = run_test(test, i)
        results.append(result)
        # Small pause between calls to avoid overwhelming the CPU
        time.sleep(2)

    total_time = time.time() - total_start

    # Calculate stats
    verdict_tests = [r for r in results if r["expected"] is not None]
    passed = sum(1 for r in verdict_tests if r["passed"])
    accuracy = passed / len(verdict_tests) * 100 if verdict_tests else 0
    open_ended = [r for r in results if r["expected"] is None]
    open_passed = sum(1 for r in open_ended if r["passed"])

    # Save JSON results
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "baseline_accuracy": 94.3,
            "veles_agent_accuracy": round(accuracy, 1),
            "total_tests": len(results),
            "verdict_tests": len(verdict_tests),
            "verdict_passed": passed,
            "open_ended_passed": f"{open_passed}/{len(open_ended)}",
            "total_time_s": round(total_time, 1),
            "results": results,
        }, f, indent=2, ensure_ascii=False)

    # Save human-readable report
    report_lines = [
        "=" * 65,
        "  VELES FINANCE AGENT — BENCHMARK REPORT",
        f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 65,
        "",
        "RESULTS BY TEST CASE:",
        "-" * 65,
    ]

    for r in results:
        icon = "+" if r["passed"] else "-"
        verdict_str = f"expected={r['expected']} got={r['got']}" if r["expected"] else "open-ended"
        report_lines.append(f"  {icon} [{r['idx']:02d}] {r['ticker']:6s} | {verdict_str} | {r['time_s']}s")
        if r["error"]:
            report_lines.append(f"      ERROR: {r['error']}")

    report_lines += [
        "",
        "=" * 65,
        "SUMMARY",
        "-" * 65,
        f"  Verdict accuracy:  {passed}/{len(verdict_tests)} = {accuracy:.1f}%",
        f"  Baseline (v5):     94.3%",
        f"  Difference:        {accuracy - 94.3:+.1f}%",
        f"  Open-ended tests:  {open_passed}/{len(open_ended)} passed",
        f"  Total time:        {total_time/60:.1f} min",
        "=" * 65,
    ]

    failures = [r for r in verdict_tests if not r["passed"]]
    if failures:
        report_lines += ["", "FAILURES:", "-" * 65]
        for r in failures:
            report_lines.append(f"  [{r['idx']:02d}] {r['ticker']} — expected {r['expected']}, got {r['got']}")
            report_lines.append(f"       Preview: {r['response_preview'][:200]}")

    report_text = "\n".join(report_lines)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(report_text)

    print()
    print(report_text)
    print(f"\nResults saved to: {RESULTS_FILE}")
    print(f"Report saved to:  {REPORT_FILE}")


if __name__ == "__main__":
    main()
