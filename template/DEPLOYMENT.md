# Deploying Your Finance AI Model on RunPod

End-to-end guide: rent a GPU → generate training data → fine-tune → push to HuggingFace.
**Total cost: ~$3–6 for a full run (8–15 hrs × $0.40/hr).**

---

## Prerequisites (do this on your local machine first)

```bash
# 1. Create HuggingFace account at https://huggingface.co
#    Get your write token: https://huggingface.co/settings/tokens
#    Save it — you'll need HF_TOKEN later.

# 2. Create a free OpenRouter account at https://openrouter.ai
#    Get API key for data generation (free tier: Qwen 72B is free).

# 3. Have your project repo ready (this repo)
```

---

## Step 1 — Rent a RunPod RTX 4090

1. Go to **https://runpod.io** → sign up → add credits ($10 minimum)

2. Click **"Deploy"** → **"GPU Pods"**

3. Filter: **RTX 4090** → sort by price → pick cheapest **Secure Cloud** pod
   - Look for **~$0.40/hr** (community cloud is cheaper but less reliable)
   - Template: **"RunPod PyTorch 2.1"** or **"RunPod Stable Diffusion"** (both work)

4. Configure:
   ```
   GPU:          1× RTX 4090 (24 GB)
   Container:    runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04
   Disk:         50 GB (enough for model + data)
   Volume:       20 GB (optional, persists across pod restarts)
   ```

5. Click **"Deploy"** → wait ~2 minutes → click **"Connect"** → **"Start Web Terminal"**

---

## Step 2 — Set Up the Environment

Run these in the RunPod terminal:

```bash
# Clone your repo
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
cd YOUR_REPO

# Install Unsloth (GPU-optimised fine-tuning)
pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
pip install --no-deps trl peft accelerate bitsandbytes

# Install data generation deps
pip install openai yfinance rich

# Install HuggingFace Hub for pushing the model
pip install huggingface_hub

# Verify GPU is visible
python -c "import torch; print(torch.cuda.get_device_name(0))"
# Expected: NVIDIA GeForce RTX 4090

# Verify Unsloth
python -c "from unsloth import FastLanguageModel; print('Unsloth OK')"
```

---

## Step 3 — Generate Training Data (SIPDO Loop)

```bash
# Set your API keys
export OPENAI_API_KEY="sk-or-YOUR_OPENROUTER_KEY"
export OPENAI_BASE_URL="https://openrouter.ai/api/v1"

# Generate 200 verified financial Q&A pairs
# ~30–60 minutes, uses free Qwen 72B on OpenRouter
python scripts/training/generate_sipdo_data.py \
    --model "qwen/qwen-2.5-72b-instruct" \
    --n 200 \
    --market_ratio 0.4 \
    --output scripts/training/finance_qa.jsonl

# Check output
wc -l scripts/training/finance_qa.jsonl      # should be ~200
head -n 1 scripts/training/finance_qa.jsonl | python -m json.tool
```

**What gets generated:**
- 120 math pairs: Kelly Criterion, Sharpe Ratio, Max Drawdown, Position Sizing
- 80 market pairs: P/E analysis, market cap, 52-week range, analyst consensus (real yfinance data)
- Each pair is verified by a deterministic math checker — wrong answers are discarded

---

## Step 4 — Fine-tune Qwen2.5-Coder-7B (QLoRA, 4-bit)

```bash
export HF_TOKEN="hf_YOUR_HUGGINGFACE_WRITE_TOKEN"

# Fine-tune (~15–25 minutes on RTX 4090)
python scripts/training/unsloth_qlora_train.py \
    --model qwen2.5-coder-7b \
    --data scripts/training/finance_qa.jsonl \
    --output outputs/finance-qwen-v1 \
    --epochs 3 \
    --push_to_hub "YOUR_HF_USERNAME/finance-qwen-7b"
```

**What happens:**
1. Downloads `unsloth/Qwen2.5-Coder-7B-Instruct-bnb-4bit` (~4 GB)
2. Applies LoRA adapters (r=16, α=32, RSLoRA) — only ~0.5% of params trainable
3. Trains on 200 financial + 26 general pairs for 3 epochs
4. Saves LoRA adapter (~120 MB) to `outputs/finance-qwen-v1/lora_adapter/`
5. Merges adapter into base model (full 16-bit weights, ~14 GB)
6. Pushes merged model to HuggingFace Hub

**Expected output:**
```
[1/6] Loading model in 4-bit (QLoRA)...
[2/6] Applying LoRA adapters (r=16, α=32, RSLoRA)...
[3/6] Loading SIPDO dataset...
  Math pairs:   120
  Market pairs: 80
  General mix:  26 (13% anti-forgetting)
  Total:        226 training pairs
[4/6] Configuring SFTTrainer...
[5/6] Training...
  step  10 | loss: 1.82
  step  20 | loss: 1.54
  ...
  Duration:  18.3 min
  Final loss: 0.94
[6/6] Merging adapter into base model...
  Published: https://huggingface.co/YOUR_USERNAME/finance-qwen-7b
```

---

## Step 5 — Download the Adapter (optional, if not pushing to HF)

If you didn't use `--push_to_hub`, download the adapter to your local machine:

```bash
# In a NEW local terminal (not RunPod):
scp -r root@YOUR_POD_IP:/root/YOUR_REPO/outputs/finance-qwen-v1/lora_adapter ./
```

Or zip and download via RunPod's file manager.

---

## Step 6 — Verify Your Model on HuggingFace

```python
# Test your published model
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

model_id = "YOUR_HF_USERNAME/finance-qwen-7b"
tok = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=torch.float16, device_map="auto")

messages = [
    {"role": "system", "content": "You are a precise quantitative finance expert."},
    {"role": "user", "content": "A trader has a 60% win rate and 2x payout ratio. What is the Kelly fraction?"},
]
inputs = tok.apply_chat_template(messages, return_tensors="pt", add_generation_prompt=True)
out = model.generate(inputs, max_new_tokens=200, temperature=0.1)
print(tok.decode(out[0][inputs.shape[1]:], skip_special_tokens=True))
# Expected: "f* = (0.6 × 2 - 0.4) / 2 = 0.40 = 40% of capital..."
```

---

## Cost Breakdown

| Step | Time | Cost |
|------|------|------|
| Data generation (200 pairs) | ~45 min | $0.30 (OpenRouter Qwen 72B is free!) |
| Fine-tuning (3 epochs, RTX 4090) | ~20 min | $0.13 |
| Pod idle time (setup, debug) | ~2 hrs | $0.80 |
| **Total** | **~3 hrs** | **~$1.23** |

> **Tip:** Stop the pod when not training (`pod → stop`). You won't be charged while stopped.
> Your files persist on the volume disk.

---

## Troubleshooting

**CUDA OOM (Out of Memory):**
```bash
# Reduce batch size
python unsloth_qlora_train.py --model qwen2.5-coder-7b ...
# Edit the script: per_device_train_batch_size=1, gradient_accumulation_steps=8
```

**Unsloth install fails:**
```bash
# Try the pip version instead
pip install unsloth
```

**HuggingFace push fails:**
```bash
# Login interactively
huggingface-cli login
# Then re-run with --push_to_hub
```

**yfinance data unavailable (firewall):**
```bash
# RunPod has internet access — should work
# If not, generate data locally first, then upload the JSONL
```

---

## Using Your Model in the Agent

Update `.env.development` to use your fine-tuned model:

```bash
# Replace the default LLM with your fine-tuned model
OPENAI_BASE_URL=https://api.together.xyz/v1   # or vLLM endpoint
DEFAULT_LLM_MODEL=YOUR_HF_USERNAME/finance-qwen-7b
```

Or serve locally with vLLM:
```bash
pip install vllm
vllm serve YOUR_HF_USERNAME/finance-qwen-7b --port 8001
# Then set OPENAI_BASE_URL=http://localhost:8001/v1
```
