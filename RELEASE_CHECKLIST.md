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

- [x] **End-to-end payment mechanics test (testnet)** — full cycle verified 2026-07-02: client received 402, signed & paid, gateway settled, wallet balance dropped by exactly $0.01 on-chain (Base Sepolia). Confirms the client → gateway → facilitator → settlement path works.
- [ ] **End-to-end real payment test (mainnet)** — same test with real USDC on Base mainnet. Not something Claude will execute (financial transaction) — do this yourself when convenient. Not urgent: mechanics already proven on testnet with identical code path.
- [x] **Rotate `PAY_TO_ADDRESS` wallet** — the private key for the old receiving wallet (`0x115D1eCC5aDF0E43a74910FE6EbceAf38b806aA0`) was exposed in a terminal/screenshot during testing (2026-07-02), while it held $0. Rotated same day to `0xB686091302926c03D44d37C02A4183601F1F56B2` (generated client-side in MetaMask, key never left the user's machine). Updated via `flyctl secrets set PAY_TO_ADDRESS=...`, the `gateway.py` fallback default, and `static/x402.json`.
- [x] **Sync `static/x402.json` with production config** — was still pointing at testnet network/facilitator/asset while the live gateway runs on Base mainnet via PayAI. Fixed 2026-07-02 (network, asset contract, facilitator URL, and `payTo` all now match `gateway.py` mainnet defaults).
- [x] **Wire chat UI to the real gateway** — `ui_kits/veles-chat/ChatScreen.jsx` now calls a real backend (`POST /web/agent`) instead of the old `setTimeout` mock; verified end-to-end in browser preview 2026-07-02 (message → gateway → backend → real reply rendered, no console errors). Added a new `/web/agent` route in `gateway.py`, deliberately outside `_ROUTES` so the x402 middleware never gates it — protected instead by a `WEB_SHARED_SECRET` header check.
- [x] **Deploy frontend publicly** — deployed to Vercel (project `veles-chat`, team `andrews-projects-371e469c`) 2026-07-02. Production URL: `https://veles-chat-m1i39cjqj-andrews-projects-371e469c.vercel.app` (the `*.vercel.app` URL itself is behind Vercel's SSO wall by design — only the custom domain bypasses it, see below).
- [x] **Custom domain purchased** — `velesfin.com` registered via Namecheap (2026-07-02) and added to the Vercel project.
- [ ] **Connect `velesfin.com` DNS** — Vercel needs one of: (a) an `A` record `velesfin.com → 76.76.21.21` on Namecheap [recommended, simpler], or (b) nameservers changed to `ns1.vercel-dns.com` / `ns2.vercel-dns.com`. This is a Namecheap-side action only the account owner can do. Once live, `velesfin.com` bypasses the SSO wall automatically (project's `ssoProtection.deploymentType` is `all_except_custom_domains`).
- [ ] **Replace the `WEB_SHARED_SECRET` stopgap with real subscription auth** — current secret is committed in `ui_kits/veles-chat/index.html` in plain sight (tried a build-time-substitution and a serverless-function approach first; both hit Vercel zero-config detection issues not worth fighting for a placeholder). Anyone reading the page source can call `/web/agent` for free right now. Must be replaced with a per-user session/token issued after MoR checkout — blocked on the MoR application (line below), not something to build in code ahead of that. **Partial mitigation added 2026-07-05**: `gateway.py` now enforces a global daily cap (`WEB_AGENT_GLOBAL_DAILY_CAP`, default 500/day) across all callers combined, on top of the existing per-IP limit — this closes the gap where a leaked secret used from many different IPs (posted publicly, botnet replay) bypassed the per-IP limiter entirely. Bounds worst-case cost exposure; does not stop abuse from a single IP within the caps, and is not a substitute for real auth.
- [x] **Point `/web/agent` at the real backend** — no separate work needed: it reuses the same `_proxy_body("/agent", ...)` helper the existing x402-gated `/agent` route uses, so it already targets whatever `RUNPOD_ENDPOINT_URL` is configured in production. The local-stub testing earlier only used a temporary env override for local verification.
- [x] **Browser payment method decision** — 2026-07-02: human users pay via a Merchant of Record (e.g. Paddle/Lemon Squeezy), not x402/crypto in-browser (x402 stays reserved for API/MCP/agent consumers).
- [ ] **MoR application** — user applying to multiple MoR providers with an honest business description ("AI research/analytics tool", not "financial advice"). Only the account owner can do this (KYC/bank details required).
- [x] **Site copy/positioning pass** — applied 2026-07-02 to `static/x402.json`: top-level description and all four endpoint descriptions reworded (no more "verdict (APPROVED/REJECTED)" language, added informational-purposes framing). Still TODO if wanted: same pass on README and the UI kit's own landing copy (currently the chat has no marketing/landing page, just the app).
- [ ] **CDP / business account** (optional) — only needed if you later want Coinbase's facilitator instead of PayAI (e.g. for higher volume than PayAI's 10k free settlements/month, or Coinbase's compliance tooling).

## Notes

- **CI now blocks `build-and-push` on two gates** (`docker-publish.yml`): `eval-orchestrator` (tool-routing regression via Groq) and `regression-tests` (token-efficiency + S3 WORM audit tests, moto-mocked, no AWS/GPU needed). Neither one validates the fine-tuned model's own accuracy — `eval_v6.py` loads the 7B checkpoint via unsloth/CUDA and needs a real GPU, which standard GitHub-hosted runners don't have. **Run `eval_v6.py` by hand on the training GPU box before promoting any new adapter/merge to production** — it is not, and currently cannot be, part of the automated Docker CI.
- Gateway facilitator/network are env-var configurable (`X402_FACILITATOR_URL`, `X402_NETWORK`) — switching facilitators again needs no code change, just `flyctl secrets set`.
- RunPod GPU type (24GB) has shown "Low Supply" availability warnings during rollouts — if this becomes a recurring problem, consider enabling more GPU types in endpoint config (RTX 3090, L4, A5000 are already enabled) or increasing max workers.
