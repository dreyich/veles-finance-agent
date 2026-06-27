#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Veles Finance — QLoRA fine-tune on RunPod A40
# Model:   Qwen2.5-Coder-7B-Instruct (4-bit, ~6GB VRAM)
# Dataset: golden_train_v1.jsonl  (80 examples, upload before running)
# Time:    ~8-12 min on A40 48GB
#
# HOW TO USE:
#   1. Upload golden_train_v1.jsonl to /workspace/ via Jupyter file browser
#   2. Open a Terminal in Jupyter
#   3. bash /workspace/runpod_finetune.sh
# ─────────────────────────────────────────────────────────────────────────────
set -e

DATASET="/workspace/golden_train_v1.jsonl"
ADAPTER_OUT="/workspace/adapters/qwen-coder-7b-finance-v1"
LOG_FILE="/workspace/train_log.txt"

echo "=== Veles Finance Fine-tune ==="
echo "Dataset : $DATASET"
echo "Output  : $ADAPTER_OUT"
echo ""

# ── 1. Check dataset exists ───────────────────────────────────────────────────
if [ ! -f "$DATASET" ]; then
    echo "ERROR: $DATASET not found."
    echo "Upload golden_train_v1.jsonl via Jupyter file browser first."
    exit 1
fi
EXAMPLES=$(wc -l < "$DATASET")
echo "Dataset: $EXAMPLES examples found"

# ── 2. Install deps (skip if already installed) ───────────────────────────────
echo ""
echo "[1/4] Checking dependencies..."
python -c "import unsloth" 2>/dev/null || {
    echo "Installing unsloth..."
    pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git" -q
    pip install trl transformers datasets accelerate -q
}
echo "deps OK"

# ── 3. Run training ───────────────────────────────────────────────────────────
echo ""
echo "[2/4] Starting training..."
mkdir -p "$ADAPTER_OUT"

python - <<'PYEOF' 2>&1 | tee "$LOG_FILE"
import json, os, sys
from pathlib import Path

DATASET   = "/workspace/golden_train_v1.jsonl"
OUT_DIR   = "/workspace/adapters/qwen-coder-7b-finance-v1"
MODEL     = "unsloth/Qwen2.5-Coder-7B-Instruct-bnb-4bit"
MAX_SEQ   = 4096
LORA_RANK = 16
LORA_ALPHA= 32
LR        = 2e-4
EPOCHS    = 5
BATCH     = 2
GRAD_ACC  = 8   # effective batch = 16

print(f"Model:   {MODEL}")
print(f"Dataset: {DATASET}")
print(f"Epochs:  {EPOCHS}  |  LR: {LR}  |  LoRA r={LORA_RANK}")
print("")

# ── Load model ────────────────────────────────────────────────────────────────
from unsloth import FastLanguageModel, is_bfloat16_supported

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=MODEL,
    max_seq_length=MAX_SEQ,
    load_in_4bit=True,
    dtype=None,
)

model = FastLanguageModel.get_peft_model(
    model,
    r=LORA_RANK,
    lora_alpha=LORA_ALPHA,
    target_modules=["q_proj","k_proj","v_proj","o_proj",
                    "gate_proj","up_proj","down_proj"],
    lora_dropout=0.05,
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=42,
)

# ── Format dataset ────────────────────────────────────────────────────────────
_role = {"human": "user", "gpt": "assistant", "system": "system"}

def to_chatml(example):
    parts = []
    for turn in example["conversations"]:
        role = _role.get(turn["from"], turn["from"])
        parts.append(f"<|im_start|>{role}\n{turn['value']}<|im_end|>")
    return "\n".join(parts) + tokenizer.eos_token

examples = []
with open(DATASET, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            examples.append(json.loads(line))

texts = [to_chatml(ex) for ex in examples]
print(f"Loaded {len(texts)} examples")
print(f"Sample (first 200 chars): {texts[0][:200]}")
print("")

# Sanity-check: longest example
max_len = max(len(tokenizer.encode(t)) for t in texts)
print(f"Longest example: {max_len} tokens (max_seq={MAX_SEQ})")
if max_len > MAX_SEQ:
    print("WARNING: some examples exceed max_seq_length and will be truncated!")

from datasets import Dataset
from trl import SFTTrainer
from transformers import TrainingArguments

dataset = Dataset.from_dict({"text": texts})

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    dataset_text_field="text",
    max_seq_length=MAX_SEQ,
    dataset_num_proc=2,
    args=TrainingArguments(
        per_device_train_batch_size=BATCH,
        gradient_accumulation_steps=GRAD_ACC,
        warmup_ratio=0.1,
        num_train_epochs=EPOCHS,
        learning_rate=LR,
        fp16=not is_bfloat16_supported(),
        bf16=is_bfloat16_supported(),
        logging_steps=5,
        optim="adamw_8bit",
        weight_decay=0.01,
        lr_scheduler_type="cosine",
        seed=42,
        output_dir=OUT_DIR + "/checkpoints",
        save_strategy="epoch",
        report_to="none",
    ),
)

print("[3/4] Training started...")
stats = trainer.train()
print(f"\nTraining complete!")
print(f"  Final loss     : {stats.training_loss:.4f}")
print(f"  Runtime        : {stats.metrics.get('train_runtime', 0):.0f}s")
print(f"  Steps/sec      : {stats.metrics.get('train_steps_per_second', 0):.2f}")

# ── Save adapter ──────────────────────────────────────────────────────────────
adapter_path = OUT_DIR + "/adapter"
model.save_pretrained(adapter_path)
tokenizer.save_pretrained(adapter_path)

report = {
    "model": MODEL,
    "dataset": DATASET,
    "examples": len(texts),
    "epochs": EPOCHS,
    "lora_rank": LORA_RANK,
    "final_loss": round(stats.training_loss, 4),
    "runtime_s": round(stats.metrics.get("train_runtime", 0)),
    "adapter_path": adapter_path,
}
Path(OUT_DIR + "/train_report.json").write_text(json.dumps(report, indent=2))
print(f"\n[4/4] Adapter saved: {adapter_path}")
print(json.dumps(report, indent=2))
PYEOF

echo ""
echo "=== Done! ==="
echo "Adapter: $ADAPTER_OUT/adapter"
echo "Log:     $LOG_FILE"
echo ""
echo "Next: run quick inference test:"
echo "  python /workspace/test_adapter.py"
