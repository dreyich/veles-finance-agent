#!/usr/bin/env python3
"""
Merge Veles LoRA adapter with Qwen2.5-Coder-7B-Instruct base model.

Needed before SGLang deployment: SGLang loads full HF models, not adapters.

Usage (on RunPod A40 with 48GB VRAM):
    pip install peft transformers accelerate -q
    python merge_veles.py

Output: /workspace/veles-merged  (HuggingFace format, ~14GB)
"""
import os
import sys
import json
from pathlib import Path

BASE_MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"
ADAPTER_ID = os.getenv("VELES_ADAPTER_HF", "Drushka/Veles-Finance-7B-v5")
OUTPUT_DIR = os.getenv("VELES_MERGED_PATH", "/workspace/veles-merged")
HF_TOKEN = os.getenv("HF_TOKEN", "")


def merge():
    print(f"Base:    {BASE_MODEL}")
    print(f"Adapter: {ADAPTER_ID}")
    print(f"Output:  {OUTPUT_DIR}")
    print()

    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    import torch

    # Check if already merged
    if Path(OUTPUT_DIR).exists() and (Path(OUTPUT_DIR) / "config.json").exists():
        print(f"Merged model already exists at {OUTPUT_DIR} — skipping merge.")
        print("Delete the directory to re-merge.")
        return

    print("[1/4] Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(
        BASE_MODEL,
        trust_remote_code=True,
        token=HF_TOKEN or None,
    )

    print("[2/4] Loading base model in bf16 (no quantization for merge)...")
    base = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
        token=HF_TOKEN or None,
    )

    print(f"[3/4] Loading LoRA adapter from {ADAPTER_ID}...")
    from peft import PeftModel
    model = PeftModel.from_pretrained(
        base,
        ADAPTER_ID,
        token=HF_TOKEN or None,
    )

    print("[4/4] Merging weights and saving...")
    merged = model.merge_and_unload()
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(OUTPUT_DIR, safe_serialization=True)
    tokenizer.save_pretrained(OUTPUT_DIR)

    # Write metadata
    meta = {
        "base_model": BASE_MODEL,
        "adapter": ADAPTER_ID,
        "merged_at": str(Path(OUTPUT_DIR).stat().st_mtime),
        "format": "safetensors",
    }
    (Path(OUTPUT_DIR) / "veles_merge_info.json").write_text(json.dumps(meta, indent=2))

    size_gb = sum(f.stat().st_size for f in Path(OUTPUT_DIR).rglob("*.safetensors")) / 1e9
    print(f"\nDone! Merged model: {OUTPUT_DIR} ({size_gb:.1f} GB)")
    print("Next: run deploy/runpod_sglang.sh")


if __name__ == "__main__":
    merge()
