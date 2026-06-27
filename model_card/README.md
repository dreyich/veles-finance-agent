---
language:
- en
license: apache-2.0
base_model:
- unsloth/Qwen2.5-32B-Instruct-bnb-4bit
tags:
- finance
- due-diligence
- financial-analysis
- lora
- peft
- qwen2.5
- fintech
- investment-analysis
- langchain
- langgraph
pipeline_tag: text-generation
library_name: peft
---

# Veles-Finance-32B-LoRA

**The first open-source financial model that gives you a verdict, not an essay.**

Veles is a QLoRA adapter for Qwen2.5-32B fine-tuned on institutional-grade Due Diligence reasoning. It fetches real market data, reasons transparently, and always ends with a hard **APPROVED ✓** or **REJECTED ✗** — never a hedge.

> GPT-4 gives you "on one hand... on the other hand..."  
> Veles gives you: `VERDICT: REJECTED ✗ — P/E 45x exceeds conservative threshold`

---

## What makes it different

| | GPT-4 / Claude | **Veles** |
|---|---|---|
| Market data | Hallucinated from training | Live yfinance — deterministic |
| Verdict | Hedged, ambiguous | APPROVED or REJECTED — enforced |
| Reasoning | Hidden | `<thinking>` tags — fully visible |
| Position sizing | Estimated | Kelly Criterion (mathematical) |
| Catastrophic forgetting | N/A | Mitigated via FinCoT + QLoRA |

---

## Example output

```
User: Analyze NVDA for a conservative investor

<thinking>
  Fetching live data via yfinance...
  P/E ratio: 45.2 — high for conservative profile (threshold: 25x)
  Beta: 1.64 — significant volatility
  Profit margin: 55% — exceptional
  Conservative ceiling: 5% max position
  Decision: P/E and beta both exceed conservative thresholds
</thinking>

╔══════════════════════════════════════════════════════╗
║         INSTITUTIONAL DUE DILIGENCE REPORT           ║
╚══════════════════════════════════════════════════════╝

  Company:       NVIDIA Corporation (NVDA)
  Risk Profile:  Conservative

── Fundamentals ───────────────────────────────────────
  Trailing P/E:   45.2
  Beta:           1.64
  Profit Margin:  55.0%
  Market Cap:     $2.15T

── Strengths ──────────────────────────────────────────
  + Monopoly position in AI GPU market (>80% share)
  + 55% net profit margin — best in sector
  + Revenue +122% YoY driven by data center demand

── Risks ──────────────────────────────────────────────
  - P/E 45x is 80% above conservative threshold of 25x
  - Beta 1.64 implies 64% more volatility than S&P500
  - Cyclical semiconductor exposure to export restrictions

══════════════════════════════════════════════════════
  VERDICT:  REJECTED ✗

  P/E ratio of 45x and beta of 1.64 exceed conservative
  thresholds — unsuitable for capital-preservation mandate.
══════════════════════════════════════════════════════
```

---

## Architecture

The adapter introduces **FinCoT** (Financial Chain-of-Thought) — a reasoning protocol that forces the model to:

1. Separate internal reasoning (`<thinking>`) from final output (`<output>`)
2. Always conclude with a binary APPROVED/REJECTED verdict
3. Reference specific numbers, never vague language
4. Follow a structured Due Diligence framework across 6 dimensions:
   - Corporate overview & industry classification
   - Financial statement analysis (P&L, balance sheet, cash flow)
   - Credit risk & rating agency signals
   - Corporate governance & management quality
   - Valuation (DCF, multiples, relative)
   - Suitability against investor risk profile

### Catastrophic forgetting mitigation

Training on financial domain data risks overwriting general capabilities. We mitigated this by:
- **QLoRA rank r=16, alpha=32** — low-rank adaptation preserves base weights
- **4-bit quantization** — bnb-4bit keeps memory footprint minimal
- **Mixed dataset** — financial examples interleaved with general reasoning samples (20:80 ratio during warmup)
- **Conservative learning rate** — 2e-4 with cosine schedule and 10% warmup

---

## Training details

| Parameter | Value |
|---|---|
| Base model | `unsloth/Qwen2.5-32B-Instruct-bnb-4bit` |
| Framework | Unsloth (2x faster than HF PEFT) |
| LoRA rank | 16 |
| LoRA alpha | 32 |
| Target modules | q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj |
| Quantization | 4-bit (bnb) |
| Learning rate | 2e-4 |
| Batch size | 4 (gradient accumulation ×4) |
| Epochs | 3 |
| Dataset | finance_qa.jsonl — institutional DD cases with real market data |
| Hardware | NVIDIA A100 80GB (RunPod) |

---

## How to use

### With the full agent stack (recommended)

```bash
git clone https://github.com/Drushka/veles-finance-agent
cd veles-finance-agent
cp .env.example .env.development
# Set OPENAI_BASE_URL to your vLLM endpoint running this adapter
make docker-up
```

### Direct inference with vLLM

```bash
# Load base model + adapter
vllm serve Qwen/Qwen2.5-32B-Instruct \
  --enable-lora \
  --lora-modules veles=Drushka/Veles-Finance-32B-LoRA \
  --max-lora-rank 16
```

### With Unsloth (training / fine-tuning)

```python
from unsloth import FastLanguageModel

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="Drushka/Veles-Finance-32B-LoRA",
    max_seq_length=4096,
    load_in_4bit=True,
)
FastLanguageModel.for_inference(model)
```

### System prompt (FinCoT)

For best results, use this system prompt:

```
You are an institutional Due Diligence analyst. 
Reason entirely within <thinking> tags.
Deliver your final report within <output> tags.
Every report MUST end with VERDICT: APPROVED ✓ or VERDICT: REJECTED ✗
Never hedge. Never use "it depends". Always give a verdict.
```

---

## Benchmarks

| Task | GPT-4o | Qwen2.5-32B base | **Veles** |
|---|---|---|---|
| Verdict consistency (APPROVED/REJECTED) | 61% | 43% | **97%** |
| Correct tool call for live data | 78% | 52% | **94%** |
| No hallucinated figures | 71% | 58% | **99%** |
| FinCoT format compliance | 34% | 21% | **98%** |

*Evaluated on 200 held-out DD cases with verified market data (June 2026)*

---

## Intended use & limitations

**Intended for:**
- Financial analysts building automated screening tools
- Developers integrating structured financial reasoning into applications
- Researchers studying domain-specific fine-tuning

**Not intended for:**
- Direct investment decisions without human review
- Regulated investment advice (not a registered investment advisor)
- Real-time trading systems

**Limitations:**
- Knowledge cutoff from training data — always use with live data tools (yfinance, Bloomberg API)
- Focused on equity due diligence; limited coverage of derivatives, crypto, fixed income
- English only

---

## Roadmap

- **v2** — Portfolio analysis (multi-ticker correlation, allocation optimizer)
- **v3** — Earnings call reader (transcript → signal extraction)
- **v4** — Macro overlay (Fed, NBU, ECB rate decisions → impact on positions)

---

## Citation

```bibtex
@misc{veles-finance-2026,
  author = {Drushka},
  title = {Veles-Finance-32B-LoRA: Open-Source Institutional Due Diligence Agent},
  year = {2026},
  publisher = {HuggingFace},
  url = {https://huggingface.co/Drushka/Veles-Finance-32B-LoRA}
}
```

---

## License

Apache 2.0 — use freely, commercial use permitted, attribution appreciated.
