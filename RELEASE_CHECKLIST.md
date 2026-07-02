# Release Checklist — Veles Finance Agent

Last updated: 2026-07-02

## ✅ Done

- [x] RunPod crash-loop fixed (`fastapi_x402` bogus import removed from `main.py`)
- [x] RunPod image `v4` deployed, rollout clean, no crash-looping workers
- [x] GitHub Actions CI pipeline for building/pushing the RunPod image (`.github/workflows/docker-publish.yml`)
- [x] `.dockerignore` fixed (was pulling `venv_unsloth/`, `template/` into build context)
- [x] Trace logs persisted to network volume (`/runpod-volume/traces.jsonl`) instead of ephemeral disk
- [x] Gateway (`veles-finance-gateway.fly.dev`) switched to **Base mainnet** (`eip155:8453`) via **PayAI facilitator** — no business account needed
- [x] `PAY_TO_ADDRESS` wallet ownership confirmed by user
- [x] Live-verified: `/kelly` returns HTTP 402 with correct mainnet USDC payment requirements pointing to the confirmed wallet
- [x] MCP server published (PyPI v1.0.1 + MCP Registry)

## 🔲 Still open

- [ ] **End-to-end real payment test** — send one real (small) USDC payment through the gateway to confirm settlement actually lands in the wallet. Not something Claude will execute (financial transaction) — do this yourself.
- [ ] **Public frontend** — no UI is deployed (the Vercel frontend from the original plan was never built). Current release path is API + MCP server only, which is enough for AI-agent consumers but not human users.
- [ ] **Custom domain** — currently on `*.fly.dev` / `*.runpod.ai`. Not blocking, purely cosmetic.
- [ ] **CDP / business account** (optional) — only needed if you later want Coinbase's facilitator instead of PayAI (e.g. for higher volume than PayAI's 10k free settlements/month, or Coinbase's compliance tooling).

## Notes

- Gateway facilitator/network are env-var configurable (`X402_FACILITATOR_URL`, `X402_NETWORK`) — switching facilitators again needs no code change, just `flyctl secrets set`.
- RunPod GPU type (24GB) has shown "Low Supply" availability warnings during rollouts — if this becomes a recurring problem, consider enabling more GPU types in endpoint config (RTX 3090, L4, A5000 are already enabled) or increasing max workers.
