"""Step 2 — Fine-tune LoRA adapter with Unsloth.

Runs QLoRA training on the dataset produced by collect.py.
Designed to run on RunPod A100 or any CUDA-capable machine.

Usage:
    python -m pipeline.train --dataset pipeline/datasets/train_v2-202607_*.jsonl
    python -m pipeline.train --dataset path/to/data.jsonl --epochs 2 --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import structlog

from pipeline.config import (
    ADAPTER_DIR,
    BASE_MODEL,
    BATCH_SIZE,
    EPOCHS,
    GRAD_ACCUMULATION,
    LEARNING_RATE,
    LORA_ALPHA,
    LORA_RANK,
    LORA_TARGET_MODULES,
    MAX_SEQ_LENGTH,
    WARMUP_RATIO,
)

logger = structlog.get_logger(__name__)


def _load_dataset(path: str) -> list[dict]:
    examples = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))
    return examples


def _format_chatml(example: dict) -> str:
    """Convert conversation to Qwen ChatML format."""
    _role_map = {"human": "user", "gpt": "assistant", "system": "system"}
    parts = []
    for turn in example["conversations"]:
        role = _role_map.get(turn["from"], turn["from"])
        parts.append(f"<|im_start|>{role}\n{turn['value']}<|im_end|>")
    return "\n".join(parts)


def train(
    dataset_path: str,
    version: str,
    epochs: int = EPOCHS,
    dry_run: bool = False,
) -> Path | None:
    """Run LoRA fine-tuning. Returns path to saved adapter or None on dry run."""

    examples = _load_dataset(dataset_path)
    logger.info("train_start", examples=len(examples), version=version, epochs=epochs)

    if dry_run:
        logger.info("train_dry_run", would_train_on=len(examples))
        print(f"[DRY RUN] Would train on {len(examples)} examples for {epochs} epoch(s).")
        print(f"[DRY RUN] Base model: {BASE_MODEL}")
        print(f"[DRY RUN] LoRA rank={LORA_RANK}, alpha={LORA_ALPHA}, lr={LEARNING_RATE}")
        return None

    try:
        from unsloth import FastLanguageModel
        from unsloth import is_bfloat16_supported
        from trl import SFTTrainer
        from transformers import TrainingArguments
        from datasets import Dataset
    except ImportError:
        logger.error("train_missing_deps", hint="pip install unsloth trl transformers datasets")
        sys.exit(1)

    # ── Load base model ────────────────────────────────────────────────────────
    logger.info("train_loading_model", model=BASE_MODEL)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=MAX_SEQ_LENGTH,
        load_in_4bit=True,
        dtype=None,
    )

    # ── Apply LoRA ─────────────────────────────────────────────────────────────
    model = FastLanguageModel.get_peft_model(
        model,
        r=LORA_RANK,
        lora_alpha=LORA_ALPHA,
        target_modules=LORA_TARGET_MODULES,
        lora_dropout=0.05,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    # ── Format dataset ─────────────────────────────────────────────────────────
    texts = [_format_chatml(ex) + tokenizer.eos_token for ex in examples]
    dataset = Dataset.from_dict({"text": texts})

    # ── Training arguments ─────────────────────────────────────────────────────
    out_dir = Path(ADAPTER_DIR) / version
    out_dir.mkdir(parents=True, exist_ok=True)

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LENGTH,
        dataset_num_proc=2,
        args=TrainingArguments(
            per_device_train_batch_size=BATCH_SIZE,
            gradient_accumulation_steps=GRAD_ACCUMULATION,
            warmup_ratio=WARMUP_RATIO,
            num_train_epochs=epochs,
            learning_rate=LEARNING_RATE,
            fp16=not is_bfloat16_supported(),
            bf16=is_bfloat16_supported(),
            logging_steps=10,
            optim="adamw_8bit",
            weight_decay=0.01,
            lr_scheduler_type="cosine",
            seed=42,
            output_dir=str(out_dir / "checkpoints"),
            save_strategy="epoch",
            report_to="none",
        ),
    )

    logger.info("train_running", output_dir=str(out_dir))
    trainer_stats = trainer.train()

    # ── Save adapter ───────────────────────────────────────────────────────────
    adapter_path = out_dir / "adapter"
    model.save_pretrained(str(adapter_path))
    tokenizer.save_pretrained(str(adapter_path))

    # Save training report
    report = {
        "version": version,
        "base_model": BASE_MODEL,
        "dataset": dataset_path,
        "examples": len(examples),
        "epochs": epochs,
        "lora_rank": LORA_RANK,
        "lora_alpha": LORA_ALPHA,
        "learning_rate": LEARNING_RATE,
        "train_loss": trainer_stats.training_loss,
        "train_runtime_s": trainer_stats.metrics.get("train_runtime", 0),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "adapter_path": str(adapter_path),
    }

    report_path = out_dir / "train_report.json"
    report_path.write_text(json.dumps(report, indent=2))

    logger.info(
        "train_complete",
        adapter=str(adapter_path),
        loss=trainer_stats.training_loss,
        runtime_s=report["train_runtime_s"],
    )
    return adapter_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--version", default=f"v2-{datetime.now(timezone.utc).strftime('%Y%m%d')}")
    parser.add_argument("--epochs", type=int, default=EPOCHS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = train(args.dataset, args.version, args.epochs, args.dry_run)
    if result:
        print(f"Adapter saved: {result}")
