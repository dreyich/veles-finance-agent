"""Pipeline configuration — all tuneable knobs in one place."""

import os

# ── Data collection ────────────────────────────────────────────────────────────
MIN_QUALITY_SCORE = float(os.getenv("PIPELINE_MIN_QUALITY", "0.70"))
MIN_EXAMPLES_TO_TRAIN = int(os.getenv("PIPELINE_MIN_EXAMPLES", "200"))
MAX_EXAMPLES_PER_RUN = int(os.getenv("PIPELINE_MAX_EXAMPLES", "2000"))

# ── Training ───────────────────────────────────────────────────────────────────
BASE_MODEL = os.getenv("PIPELINE_BASE_MODEL", "unsloth/Qwen2.5-Coder-7B-Instruct-bnb-4bit")
LORA_RANK = int(os.getenv("PIPELINE_LORA_RANK", "16"))
LORA_ALPHA = int(os.getenv("PIPELINE_LORA_ALPHA", "32"))
LORA_TARGET_MODULES = [
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj",
]
LEARNING_RATE = float(os.getenv("PIPELINE_LR", "2e-4"))
BATCH_SIZE = int(os.getenv("PIPELINE_BATCH_SIZE", "4"))
GRAD_ACCUMULATION = int(os.getenv("PIPELINE_GRAD_ACCUM", "4"))
EPOCHS = int(os.getenv("PIPELINE_EPOCHS", "5"))
MAX_SEQ_LENGTH = int(os.getenv("PIPELINE_MAX_SEQ", "4096"))
WARMUP_RATIO = float(os.getenv("PIPELINE_WARMUP", "0.1"))

# ── Evaluation ─────────────────────────────────────────────────────────────────
EVAL_MIN_VERDICT_RATE = float(os.getenv("PIPELINE_EVAL_VERDICT_RATE", "0.90"))
EVAL_MIN_THINKING_RATE = float(os.getenv("PIPELINE_EVAL_THINKING_RATE", "0.85"))
EVAL_TEST_CASES_PATH = os.getenv("PIPELINE_TEST_CASES", "pipeline/test_cases.jsonl")

# ── HuggingFace deployment ─────────────────────────────────────────────────────
HF_REPO_ID = os.getenv("HF_REPO_ID", "Drushka/Veles-Finance-7B-v5")
HF_TOKEN = os.getenv("HF_TOKEN", "")
AUTO_DEPLOY = os.getenv("PIPELINE_AUTO_DEPLOY", "false").lower() == "true"

# ── Database ───────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://veles:changeme@localhost:5432/veles",
)

# ── Paths ──────────────────────────────────────────────────────────────────────
DATASET_DIR = os.getenv("PIPELINE_DATASET_DIR", "pipeline/datasets")
ADAPTER_DIR = os.getenv("PIPELINE_ADAPTER_DIR", "pipeline/adapters")
REPORTS_DIR = os.getenv("PIPELINE_REPORTS_DIR", "pipeline/reports")
