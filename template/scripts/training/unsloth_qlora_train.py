"""
Unsloth QLoRA Fine-tuning — Finance AI Agent
=============================================
Fine-tunes unsloth/Qwen2.5-Coder-7B-Instruct in 4-bit on SIPDO financial data.

Hardware: RTX 4090 24GB VRAM (~$0.40/hr on RunPod)
Time:     ~15–25 min for 200 samples, 3 epochs

Quick start (on RunPod after setup — see DEPLOYMENT.md):
  python unsloth_qlora_train.py \
    --data scripts/training/finance_qa.jsonl \
    --output outputs/finance-qwen-v1 \
    --epochs 3 \
    --push_to_hub YOUR_HF_USERNAME/finance-qwen-7b

Install on GPU instance:
  pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
  pip install --no-deps trl peft accelerate bitsandbytes
  pip install huggingface_hub
"""

import argparse
import json
import os
import random
from pathlib import Path

# ── Unsloth (GPU-only) ────────────────────────────────────────────────────────
try:
    from unsloth import FastLanguageModel
    from unsloth.chat_templates import get_chat_template

    UNSLOTH_AVAILABLE = True
except ImportError:
    UNSLOTH_AVAILABLE = False
    print("[WARN] unsloth not installed. Run on a GPU instance — see DEPLOYMENT.md")

try:
    from datasets import Dataset
    from transformers import DataCollatorForSeq2Seq, TrainingArguments
    from trl import SFTTrainer

    TRL_AVAILABLE = True
except ImportError:
    TRL_AVAILABLE = False
    print("[WARN] trl/transformers not installed")

# ── Model configs ─────────────────────────────────────────────────────────────
MODEL_CONFIGS = {
    "qwen2.5-coder-7b": {
        "model_name": "unsloth/Qwen2.5-Coder-7B-Instruct-bnb-4bit",
        "chat_template": "qwen-2.5",
        "max_seq_length": 2048,
        "description": "Qwen2.5-Coder 7B — best for financial reasoning + code (DEFAULT)",
    },
    "qwen2.5-7b": {
        "model_name": "unsloth/Qwen2.5-7B-Instruct-bnb-4bit",
        "chat_template": "qwen-2.5",
        "max_seq_length": 2048,
        "description": "Qwen2.5 7B general instruct",
    },
    "llama3.1-8b": {
        "model_name": "unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit",
        "chat_template": "llama-3",
        "max_seq_length": 2048,
        "description": "Llama 3.1 8B — strong general reasoning",
    },
    "qwen2.5-14b": {
        "model_name": "unsloth/Qwen2.5-14B-Instruct-bnb-4bit",
        "chat_template": "qwen-2.5",
        "max_seq_length": 2048,
        "description": "Qwen2.5 14B — best quality, needs 40GB+ VRAM",
    },
}

# ── LoRA config (tuned for financial reasoning on RTX 4090) ──────────────────
LORA_CONFIG = {
    "r": 16,
    "lora_alpha": 32,                        # Scale = alpha/r = 2.0
    "lora_dropout": 0.05,
    "bias": "none",
    "use_gradient_checkpointing": "unsloth",  # Saves ~30% VRAM
    "random_state": 42,
    "use_rslora": True,                       # Rank-stabilised LoRA
    "target_modules": [
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ],
}

# ── General data for anti-forgetting mixing ───────────────────────────────────
_GENERAL_PAIRS = [
    {
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is the capital of France?"},
            {"role": "assistant", "content": "The capital of France is Paris."},
        ]
    },
    {
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Explain what a derivative is in calculus."},
            {"role": "assistant", "content": (
                "A derivative measures the instantaneous rate of change of a function. "
                "For f(x), the derivative f'(x) = lim(h→0) [f(x+h) - f(x)] / h. "
                "Geometrically, it's the slope of the tangent line at any point."
            )},
        ]
    },
    {
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Write a Python function to calculate compound interest."},
            {"role": "assistant", "content": (
                "```python\ndef compound_interest(principal: float, rate: float, "
                "n: int, t: float) -> float:\n"
                "    \"\"\"A = P(1 + r/n)^(nt)\"\"\"\n"
                "    return principal * (1 + rate / n) ** (n * t)\n\n"
                "# Example: $1000 at 5% annual, compounded monthly for 10 years\n"
                "result = compound_interest(1000, 0.05, 12, 10)\n"
                "print(f'${result:.2f}')  # $1647.01\n```"
            )},
        ]
    },
    {
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is inflation and how does it affect purchasing power?"},
            {"role": "assistant", "content": (
                "Inflation is the rate at which the general level of prices for goods and "
                "services rises over time, reducing purchasing power. If inflation is 5%, "
                "a basket of goods costing $100 today will cost $105 next year — so your "
                "money buys less. Central banks target ~2% inflation as healthy for growth."
            )},
        ]
    },
]


def load_jsonl(path: str) -> list[dict]:
    data = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    data.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return data


def _get_general_data(n: int) -> list[dict]:
    result = []
    while len(result) < n:
        result.extend(_GENERAL_PAIRS)
    return result[:n]


def format_for_training(examples: list[dict], tokenizer) -> Dataset:
    texts = []
    for ex in examples:
        messages = ex.get("messages", [])
        if not messages:
            continue
        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=False,
        )
        texts.append({"text": text})
    return Dataset.from_list(texts)


def train(args) -> None:
    if not UNSLOTH_AVAILABLE or not TRL_AVAILABLE:
        print("\n[ERROR] Install dependencies first (see DEPLOYMENT.md):")
        print('  pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"')
        print("  pip install --no-deps trl peft accelerate bitsandbytes")
        return

    config = MODEL_CONFIGS.get(args.model)
    if not config:
        print(f"[ERROR] Unknown model '{args.model}'. Choose: {list(MODEL_CONFIGS.keys())}")
        return

    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  Unsloth QLoRA Fine-tuning — Finance AI Agent")
    print(f"{sep}")
    print(f"  Base model:    {config['model_name']}")
    print(f"  Dataset:       {args.data}")
    print(f"  Epochs:        {args.epochs}")
    print(f"  Output:        {args.output}")
    print(f"  HF push:       {args.push_to_hub or 'disabled'}")
    print(f"{sep}\n")

    # ── 1. Load model in 4-bit ─────────────────────────────────────────────────
    print("[1/6] Loading model in 4-bit (QLoRA)...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=config["model_name"],
        max_seq_length=config["max_seq_length"],
        dtype=None,         # Auto: float16 on RTX, bfloat16 on A100/H100
        load_in_4bit=True,
    )
    tokenizer = get_chat_template(tokenizer, chat_template=config["chat_template"])

    # ── 2. LoRA adapters ───────────────────────────────────────────────────────
    print("[2/6] Applying LoRA adapters (r=16, α=32, RSLoRA)...")
    model = FastLanguageModel.get_peft_model(model, **LORA_CONFIG)

    # ── 3. Load dataset ────────────────────────────────────────────────────────
    print("[3/6] Loading SIPDO dataset...")
    finance_data = load_jsonl(args.data)
    if not finance_data:
        print(f"[ERROR] No data found at {args.data}")
        print("  Run generate_sipdo_data.py first.")
        return

    math_pairs = [d for d in finance_data if not d.get("metadata", {}).get("real_data")]
    market_pairs = [d for d in finance_data if d.get("metadata", {}).get("real_data")]
    print(f"  Math pairs:   {len(math_pairs)}")
    print(f"  Market pairs: {len(market_pairs)}")

    # Anti-forgetting: mix 13% general data
    n_general = max(2, int(len(finance_data) * args.general_ratio))
    general_data = _get_general_data(n_general)
    print(f"  General mix:  {n_general} ({args.general_ratio*100:.0f}% anti-forgetting)")

    all_data = finance_data + general_data
    random.shuffle(all_data)
    print(f"  Total:        {len(all_data)} training pairs")

    dataset = format_for_training(all_data, tokenizer)

    # ── 4. Trainer config ──────────────────────────────────────────────────────
    print("[4/6] Configuring SFTTrainer...")
    output_path = Path(args.output)
    output_path.mkdir(parents=True, exist_ok=True)

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=config["max_seq_length"],
        data_collator=DataCollatorForSeq2Seq(tokenizer=tokenizer, pad_to_multiple_of=8),
        dataset_num_proc=2,
        args=TrainingArguments(
            per_device_train_batch_size=2,
            gradient_accumulation_steps=4,    # Effective batch = 8
            warmup_ratio=0.05,
            num_train_epochs=args.epochs,
            learning_rate=2e-4,
            fp16=not args.bf16,
            bf16=args.bf16,                   # Use --bf16 on A100/H100
            logging_steps=5,
            optim="adamw_8bit",
            weight_decay=0.01,
            lr_scheduler_type="cosine",
            seed=42,
            output_dir=str(output_path / "checkpoints"),
            report_to="none",
            save_strategy="epoch",
            save_total_limit=2,
            dataloader_num_workers=2,
        ),
    )

    # ── 5. Train ───────────────────────────────────────────────────────────────
    print("[5/6] Training...")
    stats = trainer.train()

    # Save LoRA adapter (~80–150 MB, not the full 14 GB model)
    adapter_path = output_path / "lora_adapter"
    model.save_pretrained(str(adapter_path))
    tokenizer.save_pretrained(str(adapter_path))
    print(f"\n  Adapter saved: {adapter_path}")
    print(f"  Duration:      {stats.metrics.get('train_runtime', 0) / 60:.1f} min")
    print(f"  Final loss:    {stats.metrics.get('train_loss', 'N/A')}")

    # ── 6. Merge + push to HuggingFace ────────────────────────────────────────
    print("[6/6] Merging adapter into base model...")
    merged_path = output_path / "merged_model"

    model.save_pretrained_merged(
        str(merged_path),
        tokenizer,
        save_method="merged_16bit",   # Full precision merged weights
    )
    print(f"  Merged model: {merged_path}")

    if args.push_to_hub:
        print(f"\n  Pushing to HuggingFace Hub: {args.push_to_hub}")
        hf_token = os.getenv("HF_TOKEN", "")
        if not hf_token:
            print("  [WARN] HF_TOKEN not set. Run: export HF_TOKEN=hf_...")
        model.push_to_hub_merged(
            args.push_to_hub,
            tokenizer,
            save_method="merged_16bit",
            token=hf_token,
        )
        print(f"  Published: https://huggingface.co/{args.push_to_hub}")

    # Push LoRA adapter weights and tokenizer to Hugging Face Hub
    model.push_to_hub("YOUR_HF_USERNAME/Finance-Qwen-32B-LoRA", token=os.environ.get("HF_TOKEN"))
    tokenizer.push_to_hub("YOUR_HF_USERNAME/Finance-Qwen-32B-LoRA", token=os.environ.get("HF_TOKEN"))

    print(f"\n{'='*60}")
    print(f"  Training complete!")
    print(f"  Adapter:      {adapter_path}")
    print(f"  Merged model: {merged_path}")
    if args.push_to_hub:
        print(f"  HF Hub:       https://huggingface.co/{args.push_to_hub}")
    print(f"  LoRA adapter: https://huggingface.co/YOUR_HF_USERNAME/Finance-Qwen-32B-LoRA")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Unsloth QLoRA Financial Fine-tuning")
    parser.add_argument(
        "--model",
        default="qwen2.5-coder-7b",        # Changed from llama3.1-8b
        choices=list(MODEL_CONFIGS.keys()),
        help="Base model (default: qwen2.5-coder-7b = Qwen2.5-Coder-7B-Instruct)",
    )
    parser.add_argument("--data", default="scripts/training/finance_qa.jsonl")
    parser.add_argument("--output", default="outputs/finance-qwen-v1")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument(
        "--general_ratio", type=float, default=0.13,
        help="Fraction of general data to mix in (0.10–0.17 recommended)",
    )
    parser.add_argument(
        "--push_to_hub", default="",
        help="HuggingFace repo to push merged model (e.g. 'username/finance-qwen-7b')",
    )
    parser.add_argument(
        "--bf16", action="store_true",
        help="Use bfloat16 instead of float16 (A100/H100 only)",
    )
    args = parser.parse_args()
    train(args)


if __name__ == "__main__":
    main()
