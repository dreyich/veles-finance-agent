# Veles — Open-Source Finance AI Agent

> **GPT-4 gives you an essay. Veles gives you a verdict.**

Veles is an open-source institutional-grade Due Diligence agent built on a fine-tuned Qwen2.5-32B with LoRA. It fetches real market data, reasons transparently through `<thinking>` tags, and always ends with a hard **APPROVED ✓** or **REJECTED ✗** — never a hedge.

---

## What it does

```
User: "Analyse NVDA for a conservative investor"

<thinking>
  Fetching live data via yfinance...
  P/E 45x → high for conservative profile
  Beta 1.64 → significant volatility
  Profit margin 55% → exceptional fundamentals
  Conservative ceiling: 5% position max
  Decision: P/E and beta exceed conservative thresholds → REJECTED
</thinking>

╔══════════════════════════════════════════════════════╗
║         INSTITUTIONAL DUE DILIGENCE REPORT           ║
╚══════════════════════════════════════════════════════╝

  Company:       NVIDIA Corporation (NVDA)
  Risk Profile:  Conservative
  ...
  Trailing P/E:  45.2
  Beta:          1.64
  ...

══════════════════════════════════════
  VERDICT:  REJECTED ✗

  P/E ratio of 45x and beta of 1.64 exceed conservative
  thresholds — unsuitable for capital-preservation mandate.
══════════════════════════════════════
```

---

## Key differentiators

| | ChatGPT / GPT-4 | **Veles** |
|---|---|---|
| Market data | From training memory (can be stale) | Live yfinance — deterministic |
| Verdict | "On one hand... on the other..." | **APPROVED or REJECTED** — always |
| Reasoning | Hidden | `<thinking>` tags — fully visible |
| Position sizing | Estimated | Kelly Criterion calculator |
| Code execution | No | Python sandbox (backtests, DCF) |
| Learning | Static | Closed feedback loop per release |
| Audit trail | None | WORM-compliant audit logs |
| Token safety | Unbounded | Loop guard prevents runaway calls |

---

## Quickstart

```bash
git clone https://github.com/YOUR_USERNAME/veles-finance-agent
cd veles-finance-agent
cp .env.example .env.development   # fill in your keys
make docker-up                     # starts API + PostgreSQL
```

Open [http://localhost:8000/docs](http://localhost:8000/docs) — interactive API docs.

### Minimal `.env.development`

```env
OPENAI_API_KEY=your-key-here          # or point to your vLLM endpoint
DEFAULT_LLM_MODEL=veles               # swap for any OpenAI-compatible model
POSTGRES_DB=veles
POSTGRES_USER=veles
POSTGRES_PASSWORD=changeme
JWT_SECRET_KEY=changeme-in-production
```

---

## How it works

```
User message
    │
    ▼
┌─────────────────────────────────────────────┐
│  LangGraph Agent  (Veles / Qwen2.5-32B LoRA) │
│                                              │
│  1. get_market_data(ticker)                  │  ← yfinance, live
│  2. <thinking> — FinCoT reasoning            │  ← transparent
│  3. generate_dd_report(...)                  │  ← structured output
│  4. APPROVED ✓ / REJECTED ✗                 │  ← deterministic
└─────────────────────────────────────────────┘
    │
    ▼
PostgreSQL (conversation memory + audit log)
```

**Tools available to the agent:**
- `get_market_data` — live price, fundamentals, news via yfinance
- `generate_dd_report` — structured DD report with enforced verdict schema
- `kelly_criterion_calculator` — optimal position sizing
- `execute_python_sandbox` — isolated Python for DCF, backtests, simulations
- `duckduckgo_search` — macro context and regulatory news
- `save_trading_skill` / `list_trading_skills` — procedural memory
- `ask_human` — clarifying questions on risk profile / horizon

---

## Architecture

```
app/
  api/v1/              # REST endpoints (chat, stream, auth)
  core/
    langgraph/
      graph.py         # Agent workflow — loop guard, PII shield, audit
      tools/
        market_data_tools.py    # yfinance integration
        dd_report_tools.py      # DD report + verdict enforcement
        quantoracle_tools.py    # Kelly Criterion
        sandbox_tools.py        # E2B / local Python sandbox
        memory_tools.py         # Procedural skill memory
        schema_tools.py         # Progressive disclosure (saves ~1650 tokens/req)
    prompts/
      system.md        # FinCoT system prompt with APPROVED/REJECTED mandate
  services/
    llm/               # Circular fallback, exponential backoff, timeout budget
    memory.py          # mem0 + pgvector semantic memory
  core/
    audit_logger.py    # WORM-compliant audit traces
    pii_shield.py      # PII masking before LLM
```

### What "production-ready" means here

- **Loop guard** — `MAX_TOOL_CALLS` cap prevents infinite reasoning loops
- **PII shield** — masks personal data before it reaches the model
- **WORM audit log** — every session logged with tool calls and model used
- **Circular LLM fallback** — if primary model fails, rotates to backup automatically
- **Conversation logger** — stores Q&A pairs for the feedback learning loop
- **Long-term memory** — mem0 + pgvector remembers user preferences across sessions
- **Rate limiting** — slowapi per-route limits
- **Observability** — Langfuse traces + Prometheus metrics + Grafana dashboards

---

## Roadmap

**v1 (current)**
- [x] Due Diligence reports with APPROVED/REJECTED verdict
- [x] Live market data via yfinance (no hallucinated figures)
- [x] `<thinking>` tag transparency
- [x] Kelly Criterion position sizing
- [x] Python sandbox for DCF and backtests
- [x] WORM audit logs
- [x] Feedback loop data collection

**v2**
- [ ] Portfolio analysis (multi-ticker correlation, allocation)
- [ ] Earnings call reader (transcript summarisation + signal extraction)
- [ ] NBU / Minfin API for UAH macro context
- [ ] HuggingFace Spaces demo

**v3**
- [ ] MCP server — plug Veles tools into Claude Desktop
- [ ] Automated LoRA retraining pipeline on feedback data
- [ ] Prepaid balance billing (Stripe)

---

## Running with your own model

Veles is designed to work with any OpenAI-compatible inference endpoint.
Point `OPENAI_BASE_URL` at your vLLM / Ollama / RunPod server:

```env
OPENAI_BASE_URL=https://your-runpod-endpoint/v1
OPENAI_API_KEY=your-api-key
DEFAULT_LLM_MODEL=veles
```

No code changes needed — the agent uses LangChain's `ChatOpenAI` client.

---

## MCP Server — plug into Claude Desktop in 30 seconds

```bash
uvx veles-finance-mcp
```

Add to `~/.claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "veles-finance": {
      "command": "uvx",
      "args": ["veles-finance-mcp"]
    }
  }
}
```

Now ask Claude: *"Analyse NVDA for a conservative investor"* — it will call `due_diligence_report` and return APPROVED ✓ or REJECTED ✗.

Available MCP tools: `get_market_data`, `due_diligence_report`, `kelly_position_size`

---

## Streamlit demo

```bash
cd demo
pip install -r requirements.txt
streamlit run app.py
```

Runs against the local backend at `http://localhost:8000`. Set `VELES_API_URL` to point elsewhere.

---

## x402 Micropayments (AI-to-AI)

Veles supports the [x402 protocol](https://x402.org) — other AI agents can autonomously purchase DD reports for **$0.05 USDC** on Base (Coinbase L2).

```bash
# Enable in .env
PAYMENT_REQUIRED=true
RECEIVER_WALLET_ADDRESS=0xYourWallet
PAYMENT_AMOUNT_USDC=0.05
```

Without payment headers → `HTTP 402` with payment details. With valid proof → report served.
Both EIP-3009 authorization (x402 SDK) and direct tx hash verification are supported.

---

## Contributing

PRs welcome. Read [docs/getting-started.md](docs/getting-started.md) for local setup, then follow [AGENTS.md](AGENTS.md) for code conventions.

Report security issues privately — see [SECURITY.md](SECURITY.md).

---

## License

See [LICENSE](LICENSE).
