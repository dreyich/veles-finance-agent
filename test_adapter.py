"""
Quick sanity-check after fine-tuning.
Run on RunPod after training completes:
    python /workspace/test_adapter.py

Tests the adapter on 3 examples from the eval set (golden_v1.jsonl).
Expected: model returns clean JSON, correct signs, correct units.
"""
import json, os

ADAPTER = "/workspace/adapters/qwen-coder-7b-finance-v1/adapter"
EVAL_FILE = "/workspace/golden_v1.jsonl"   # held-out eval set

SYSTEM = (
    "You are a zero-truncation financial data extractor for SEC 10-K filings.\n\n"
    "Rules:\n"
    "- Return ONLY a valid JSON object, no prose or explanation\n"
    "- All monetary values are plain numbers in the unit stated in the source\n"
    "- Values shown in parentheses, e.g. $(156), are NEGATIVE numbers\n"
    "- Tax benefits are NEGATIVE; tax provisions are POSITIVE\n"
    "- Dates must use ISO 8601 format: YYYY-MM-DD (e.g. 2024-01-28, not 'Jan 28, 2024')\n"
    "- Month names in text answers must be fully lowercase (e.g. 'january', not 'Jan')\n"
    "- Read ALL footnotes — critical data is often ONLY in footnotes, not the main table\n"
    "- If a field cannot be found anywhere in the text, use null\n"
    "- Never hallucinate; if unsure, use null"
)

# ── Load model ────────────────────────────────────────────────────────────────
from unsloth import FastLanguageModel

print("Loading adapter...")
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=ADAPTER,
    max_seq_length=4096,
    load_in_4bit=True,
)
FastLanguageModel.for_inference(model)
print("Adapter loaded.\n")

# ── Load 3 eval examples ──────────────────────────────────────────────────────
examples = []
with open(EVAL_FILE, encoding="utf-8") as f:
    for line in f:
        if line.strip():
            examples.append(json.loads(line))

examples = examples[:10]  # all 10 eval examples

def run(system_prompt, user_prompt):
    prompt = (
        f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
        f"<|im_start|>user\n{user_prompt}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )
    inputs = tokenizer(prompt, return_tensors="pt").to("cuda")
    input_len = inputs["input_ids"].shape[1]
    outputs = model.generate(
        **inputs,
        max_new_tokens=512,
        temperature=None,
        do_sample=False,
        pad_token_id=tokenizer.eos_token_id,
    )
    # decode only the newly generated tokens (skip the prompt echo)
    return tokenizer.decode(outputs[0][input_len:], skip_special_tokens=True).strip()

# ── Score ─────────────────────────────────────────────────────────────────────
TOL = 0.02
total = correct = wrong_sign = 0

for i, ex in enumerate(examples):
    convs = ex["conversations"]
    expected = json.loads(convs[2]["value"])

    response_text = run(convs[0]["value"], convs[1]["value"])

    try:
        got = json.loads(response_text)
    except json.JSONDecodeError:
        print(f"[{i}] JSON parse FAILED")
        print(f"  Raw: {response_text[:300]}")
        continue

    ex_ok = ex_total = 0
    errors = []
    for field, exp_val in expected.items():
        got_val = got.get(field)
        if exp_val is None:
            ok = got_val is None or got_val == 0
        elif isinstance(exp_val, (int, float)):
            if got_val is None:
                ok = False
                errors.append(f"  {field}: expected {exp_val} got null")
            else:
                try:
                    fgot = float(got_val)
                    if exp_val != 0 and (exp_val > 0) != (fgot > 0):
                        ok = False
                        wrong_sign += 1
                        errors.append(f"  {field}: WRONG SIGN expected {exp_val} got {fgot}")
                    else:
                        ok = abs(fgot - exp_val) / (abs(exp_val) or 1) <= TOL
                        if not ok:
                            errors.append(f"  {field}: expected {exp_val} got {fgot}")
                except (TypeError, ValueError):
                    ok = False
                    errors.append(f"  {field}: non-numeric {got_val!r}")
        else:
            ok = str(got_val).strip().lower() == str(exp_val).strip().lower()
            if not ok:
                errors.append(f"  {field}: expected {exp_val!r} got {got_val!r}")

        ex_total += 1
        total += 1
        if ok:
            ex_ok += 1
            correct += 1

    pct = ex_ok / ex_total * 100 if ex_total else 0
    tag = "OK" if pct == 100 else ("PARTIAL" if pct >= 70 else "FAIL")
    print(f"[{i}] {pct:5.1f}% [{tag}]")
    for e in errors:
        print(e)

acc = correct / total * 100 if total else 0
print(f"\nOverall: {acc:.1f}% ({correct}/{total} fields correct)")
print(f"Wrong-sign errors: {wrong_sign}")

if acc >= 95:
    print("\nSANITY CHECK PASSED — adapter learned the format correctly.")
elif acc >= 70:
    print("\nPARTIAL — some traps missed, consider more epochs or more data.")
else:
    print("\nFAIL — check chat template, dataset format, or training loss curve.")
