"""
Fixed QLoRA fine-tune — no checkpoint saving (avoids PicklingError).
Run: python /workspace/train_v2.py
"""
import json
from pathlib import Path
from unsloth import FastLanguageModel, is_bfloat16_supported
from trl import SFTTrainer, SFTConfig
from datasets import Dataset

DATASET = "/workspace/golden_train_v1.jsonl"
OUT     = "/workspace/adapters/qwen-coder-7b-finance-v1"

print("Loading model...")
model, tokenizer = FastLanguageModel.from_pretrained(
    "unsloth/Qwen2.5-Coder-7B-Instruct-bnb-4bit",
    max_seq_length=4096,
    load_in_4bit=True,
    dtype=None,
)

model = FastLanguageModel.get_peft_model(
    model,
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    bias="none",
    target_modules=["q_proj","k_proj","v_proj","o_proj",
                    "gate_proj","up_proj","down_proj"],
    use_gradient_checkpointing="unsloth",
    random_state=42,
)

_role = {"human": "user", "gpt": "assistant", "system": "system"}

def fmt(ex):
    parts = []
    for t in ex["conversations"]:
        role = _role.get(t["from"], t["from"])
        parts.append(f"<|im_start|>{role}\n{t['value']}<|im_end|>")
    return "\n".join(parts) + tokenizer.eos_token

with open(DATASET, encoding="utf-8") as f:
    examples = [json.loads(l) for l in f if l.strip()]

dataset = Dataset.from_dict({"text": [fmt(e) for e in examples]})
print(f"Loaded {len(examples)} examples")
print(f"Longest: {max(len(tokenizer.encode(t)) for t in dataset['text'])} tokens")

Path(OUT).mkdir(parents=True, exist_ok=True)

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    dataset_text_field="text",
    max_seq_length=4096,
    args=SFTConfig(
        per_device_train_batch_size=2,
        gradient_accumulation_steps=8,
        warmup_ratio=0.1,
        num_train_epochs=5,
        learning_rate=2e-4,
        bf16=is_bfloat16_supported(),
        fp16=not is_bfloat16_supported(),
        logging_steps=3,
        optim="adamw_8bit",
        seed=42,
        output_dir=OUT + "/checkpoints",
        save_strategy="no",
        report_to="none",
    ),
)

print("Training started...")
stats = trainer.train()
print(f"\nFinal loss : {stats.training_loss:.4f}")
print(f"Runtime    : {stats.metrics.get('train_runtime', 0):.0f}s")

adapter_path = OUT + "/adapter"
model.save_pretrained(adapter_path)
tokenizer.save_pretrained(adapter_path)
print(f"Adapter saved: {adapter_path}")
