# Finance AI Agent — Fine-tuning Guide

Train a custom Llama 3.1 8B or Qwen 2.5 7B model on synthetic financial data
for under **$10** using a rented RTX 4090.

---

## Architecture Overview

```
SIPDO Loop
──────────
OpenRouter API (free)
    │
    ▼
Fin-Generator           ← generates financial scenarios
    │
    ▼
Fin-Verifier            ← checks math deterministically
    │ (pass)
    ▼
finance_qa.jsonl        ← verified QA pairs

QLoRA Training
──────────────
finance_qa.jsonl + 13% general data
    │
    ▼
Unsloth + 4-bit base model
    │
    ▼
LoRA adapter (~100 MB)  ← upload to HuggingFace or deploy via vLLM
```

---

## Step 1 — Generate Synthetic Data (Local, Free)

Run on your local machine using the free OpenRouter API key:

```bash
cd "D:\Finance AI agent\template"

# Set your OpenRouter key
set OPENAI_API_KEY=sk-or-v1-...
set OPENAI_BASE_URL=https://openrouter.ai/api/v1

# Generate 200 verified QA pairs (~15 minutes, costs $0)
python scripts/training/generate_sipdo_data.py \
  --model qwen/qwen-2.5-72b-instruct \
  --n 200 \
  --output scripts/training/finance_qa.jsonl

# Output: scripts/training/finance_qa.jsonl
# Expected pass rate: 70-85% (math verification filters wrong answers)
```

---

## Step 2 — Rent a GPU (RTX 4090)

### Option A: Vast.ai (cheapest, ~$0.20-0.50/hr)

1. Go to [vast.ai](https://vast.ai) → Create account → Add $10 credit
2. Search for instance: `RTX 4090`, `24 GB VRAM`, `PyTorch 2.x`
3. Select template: **"PyTorch 2.1 + CUDA 12.1"**
4. Click **Rent** (~$0.35/hr)
5. Connect via SSH:
```bash
ssh -p PORT root@INSTANCE_IP
```

### Option B: RunPod (easier UI, ~$0.44-0.79/hr)

1. Go to [runpod.io](https://runpod.io) → Add $10 credit
2. Click **Deploy** → **GPU Cloud** → Select **RTX 4090**
3. Template: **"RunPod PyTorch 2.1"**
4. Connect via **Web Terminal** or SSH

---

## Step 3 — Upload Data to GPU Instance

```bash
# From your local machine, upload the generated dataset
scp -P PORT scripts/training/finance_qa.jsonl root@INSTANCE_IP:/workspace/
scp -P PORT scripts/training/unsloth_qlora_train.py root@INSTANCE_IP:/workspace/
```

---

## Step 4 — Install Dependencies on GPU Instance

SSH into the instance, then:

```bash
# Install Unsloth (takes ~3 minutes)
pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
pip install --no-deps trl peft accelerate bitsandbytes

# Verify GPU is detected
python -c "import torch; print(torch.cuda.get_device_name(0))"
# Expected: NVIDIA GeForce RTX 4090
```

---

## Step 5 — Run Training

```bash
cd /workspace

# Option A: Train Llama 3.1 8B (~20 minutes on RTX 4090)
python unsloth_qlora_train.py \
  --model llama3.1-8b \
  --data finance_qa.jsonl \
  --output outputs/finance-llama-v1 \
  --epochs 3

# Option B: Train Qwen 2.5 7B (~15 minutes, better for code/math)
python unsloth_qlora_train.py \
  --model qwen2.5-7b \
  --data finance_qa.jsonl \
  --output outputs/finance-qwen-v1 \
  --epochs 3
```

**Expected output:**
```
[1/5] Loading model in 4-bit...
[2/5] Applying LoRA adapters...
[3/5] Loading dataset...
      Financial pairs: 200
      General pairs:   26 (13% ratio)
[4/5] Configuring SFTTrainer...
[5/5] Training...
      Duration: 17.3 minutes
      Final loss: 0.82
      Adapter saved: outputs/finance-qwen-v1/lora_adapter
```

---

## Step 6 — Download the Adapter

```bash
# From your local machine
scp -P PORT -r root@INSTANCE_IP:/workspace/outputs/finance-qwen-v1/lora_adapter ./

# The adapter is only ~100 MB (not the 16 GB full model)
```

---

## Step 7 — Deploy or Merge

### Quick test (local):
```python
from unsloth import FastLanguageModel

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="lora_adapter",
    max_seq_length=2048,
    load_in_4bit=True,
)

FastLanguageModel.for_inference(model)
inputs = tokenizer.apply_chat_template(
    [{"role": "user", "content": "Kelly Criterion: 60% win rate, 2.0 payout. Optimal size?"}],
    return_tensors="pt",
)
outputs = model.generate(inputs.to("cuda"), max_new_tokens=256)
print(tokenizer.decode(outputs[0]))
```

### Merge and push to HuggingFace:
```python
model.save_pretrained_merged(
    "finance-agent-merged",
    tokenizer,
    save_method="merged_16bit",
)
model.push_to_hub("your-username/finance-agent-v1", token="hf_...")
```

---

## Cost Breakdown

| Task | Time | Cost |
|------|------|------|
| Generate 200 SIPDO pairs | ~15 min | **$0** (OpenRouter free) |
| Rent RTX 4090 (Vast.ai) | 1 hour | **$0.35** |
| Install deps | 5 min | included |
| Train Qwen 2.5 7B × 3 epochs | 20 min | **$0.12** |
| Buffer time | 35 min | **$0.21** |
| **Total** | ~1 hour | **~$0.68** |

> With 500 training pairs: ~$1.50 total. Still well under $10.

---

## Anti-Forgetting Notes

The training script mixes **13% general data** by default to prevent
catastrophic forgetting. Key parameters:

```bash
--general_data_ratio 0.13   # 10-17% is the safe range
```

If the model starts forgetting general knowledge (test with "What is Paris?"):
- Increase ratio to 0.17
- Reduce epochs to 2

---

## What Changes After Fine-tuning

| Before | After |
|--------|-------|
| Needs prompting for Kelly formula | Answers directly from training |
| Occasional math errors | Verified correct patterns memorized |
| Generic financial language | Finance-specific terminology |
| Slower on tool-call format | Faster, more consistent JSON output |

The LoRA adapter adds ~**0.5-1.5% of base model parameters** — fast to load,
easy to swap, can maintain multiple domain adapters simultaneously.
