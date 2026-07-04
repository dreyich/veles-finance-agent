from __future__ import annotations
import json
import os
import pathlib
import time
from collections import defaultdict
import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from x402 import x402ResourceServer
from x402.http import HTTPFacilitatorClient
from x402.http.middleware.fastapi import payment_middleware
from x402.mechanisms.evm.exact import ExactEvmServerScheme
from x402.extensions.bazaar import declare_discovery_extension, bazaar_resource_server_extension, OutputConfig

_STATIC = pathlib.Path(__file__).parent / "static"

RUNPOD_URL = os.getenv("RUNPOD_ENDPOINT_URL", "https://n3g2m4yio8un96.api.runpod.ai")
RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY", "")
WALLET = os.getenv("PAY_TO_ADDRESS", "0xB686091302926c03D44d37C02A4183601F1F56B2")

# Shared secret for the official web frontend only — NOT a substitute for real
# subscription auth. Stopgap until MoR-issued session tokens are wired in;
# anyone who extracts this from browser JS can call /web/agent for free, so
# treat this route as provisional and add real per-user auth before public launch.
WEB_SHARED_SECRET = os.getenv("WEB_SHARED_SECRET", "")

# Per-IP rate limit for /web/agent, since the shared secret above is
# extractable from browser JS. This doesn't replace real per-user auth (a
# leaked secret still works from any IP), but it bounds how much a leaked
# secret can be abused before someone notices — in-memory, per-machine, so
# it resets on redeploy/restart, which is an acceptable tradeoff for a
# provisional route rather than pulling in Redis for this.
_WEB_AGENT_RATE_LIMIT = 30
_WEB_AGENT_RATE_WINDOW_SEC = 3600
_web_agent_calls: dict[str, list[float]] = defaultdict(list)


def _web_agent_rate_limited(client_ip: str) -> bool:
    now = time.time()
    calls = _web_agent_calls[client_ip]
    calls[:] = [t for t in calls if now - t < _WEB_AGENT_RATE_WINDOW_SEC]
    if len(calls) >= _WEB_AGENT_RATE_LIMIT:
        return True
    calls.append(now)
    return False


def _client_ip(request: Request) -> str:
    # Fly.io sets Fly-Client-IP with the real caller; request.client.host
    # would otherwise be Fly's internal proxy.
    return request.headers.get("fly-client-ip") or (request.client.host if request.client else "unknown")

# Defaults to x402.org's free testnet-only facilitator (Base Sepolia, no API key).
# For production (Base mainnet, eip155:8453), two options:
#   1. CDP (Coinbase): requires a verified Coinbase Business Account.
#      Set X402_FACILITATOR_URL=https://api.cdp.coinbase.com/platform/v2/x402
#      plus CDP_API_KEY_ID / CDP_API_KEY_SECRET env vars.
#   2. PayAI: no business verification or API key needed up to 10k
#      settlements/month. Set X402_FACILITATOR_URL=https://facilitator.payai.network
# Either way, also set X402_NETWORK=eip155:8453.
NETWORK = os.getenv("X402_NETWORK", "eip155:84532")
FACILITATOR_URL = os.getenv("X402_FACILITATOR_URL", "https://x402.org/facilitator")

# ── x402 v2 server setup ───────────────────────────────────────────────────
facilitator = HTTPFacilitatorClient({"url": FACILITATOR_URL})
x402_server = x402ResourceServer(facilitator)
x402_server.register("eip155:*", ExactEvmServerScheme())
x402_server.register_extension(bazaar_resource_server_extension)

_ACCEPTS = lambda price: {"scheme": "exact", "payTo": WALLET, "price": price, "network": NETWORK}

_ROUTES: dict = {
    "POST /agent": {
        "accepts": _ACCEPTS("$0.05"),
        "description": "Full LangGraph financial agent — routes to market data, SEC 10-K, due diligence, Kelly Criterion.",
        "extensions": declare_discovery_extension(
            input={"message": "Compare Apple revenue YoY vs Microsoft", "history": []},
            input_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "history": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["message"],
            },
            body_type="json",
            output=OutputConfig(
                example={"response": "Apple revenue grew 5% YoY to $391B vs Microsoft 16% to $245B. Apple margins are superior at 26% net vs 36% for MSFT."},
                schema={"type": "object", "properties": {"response": {"type": "string"}}},
            ),
        ),
    },
    "POST /ask": {
        "accepts": _ACCEPTS("$0.02"),
        "description": "Direct question to Veles-Finance-7B model. Best for factual financial questions.",
        "extensions": declare_discovery_extension(
            input={"message": "What is the Sharpe ratio?"},
            input_schema={
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            },
            body_type="json",
            output=OutputConfig(
                example={"response": "The Sharpe ratio measures risk-adjusted return: (portfolio return - risk free rate) / standard deviation."},
                schema={"type": "object", "properties": {"response": {"type": "string"}}},
            ),
        ),
    },
    "POST /due-diligence": {
        "accepts": _ACCEPTS("$0.02"),
        "description": "Stock screening: APPROVED/REJECTED verdict with P/E, beta, and margin analysis.",
        "extensions": declare_discovery_extension(
            input={"ticker": "AAPL", "risk_profile": "moderate"},
            input_schema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Stock ticker symbol"},
                    "risk_profile": {"type": "string", "enum": ["conservative", "moderate", "aggressive"]},
                },
                "required": ["ticker"],
            },
            output=OutputConfig(
                example={"verdict": "APPROVED", "ticker": "AAPL", "pe_ratio": 28.5, "beta": 1.19, "profit_margin": 0.26, "summary": "AAPL passes moderate risk screening."},
                schema={"type": "object", "properties": {"verdict": {"type": "string", "enum": ["APPROVED", "REJECTED"]}, "ticker": {"type": "string"}, "summary": {"type": "string"}}},
            ),
        ),
    },
    "POST /sec": {
        "accepts": _ACCEPTS("$0.02"),
        "description": "Extract key financials from latest SEC 10-K annual report via EDGAR.",
        "extensions": declare_discovery_extension(
            input={"ticker": "AAPL"},
            input_schema={
                "type": "object",
                "properties": {"ticker": {"type": "string", "description": "Stock ticker symbol"}},
                "required": ["ticker"],
            },
            output=OutputConfig(
                example={"ticker": "AAPL", "revenue": 391035000000, "net_income": 93736000000, "eps": 6.11, "debt_to_equity": 1.87, "fiscal_year": 2024},
                schema={"type": "object", "properties": {"ticker": {"type": "string"}, "revenue": {"type": "number"}, "net_income": {"type": "number"}, "eps": {"type": "number"}}},
            ),
        ),
    },
    "POST /kelly": {
        "accepts": _ACCEPTS("$0.01"),
        "description": "Kelly Criterion position sizing: optimal bet fraction given win rate and payoff ratio.",
        "extensions": declare_discovery_extension(
            input={"win_rate": 0.55, "win_loss_ratio": 1.5},
            input_schema={
                "type": "object",
                "properties": {
                    "win_rate": {"type": "number", "description": "Historical win rate (0-1)"},
                    "win_loss_ratio": {"type": "number", "description": "Avg win / avg loss ratio"},
                },
                "required": ["win_rate", "win_loss_ratio"],
            },
            output=OutputConfig(
                example={"full_kelly": 0.1833, "half_kelly": 0.0917, "win_rate": 0.55, "win_loss_ratio": 1.5},
                schema={"type": "object", "properties": {"full_kelly": {"type": "number"}, "half_kelly": {"type": "number"}}},
            ),
        ),
    },
}

# ── FastAPI app ────────────────────────────────────────────────────────────
gateway = FastAPI(
    title="Veles Finance Agent",
    version="2.0.0",
    description="AI-powered financial analysis. Pay per request in USDC on Base via x402.",
    contact={"url": "https://veles-finance-gateway.fly.dev"},
)
gateway.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Create middleware once at startup, not per-request
_x402_mw = payment_middleware(_ROUTES, x402_server)


@gateway.middleware("http")
async def x402_middleware(request: Request, call_next):
    return await _x402_mw(request, call_next)


_HEADERS = lambda: {"Authorization": f"Bearer {RUNPOD_API_KEY}"}


_COLD_START_TIMEOUT = httpx.Timeout(280.0, connect=15.0)


async def _proxy_body(path: str, body: dict) -> dict:
    async with httpx.AsyncClient(timeout=_COLD_START_TIMEOUT) as client:
        r = await client.post(f"{RUNPOD_URL}{path}", json=body, headers=_HEADERS())
        r.raise_for_status()
        return r.json()


async def _proxy_params(path: str, params: dict) -> dict:
    async with httpx.AsyncClient(timeout=_COLD_START_TIMEOUT) as client:
        r = await client.post(f"{RUNPOD_URL}{path}", params=params, headers=_HEADERS())
        r.raise_for_status()
        return r.json()


# ── Open endpoints ─────────────────────────────────────────────────────────

@gateway.get("/health")
def health():
    return {"status": "ok", "backend": RUNPOD_URL}


@gateway.post("/warm")
async def warm():
    """Pre-warming ping — called by the frontend on page load so the RunPod
    worker (and model) is already spinning up by the time the user sends
    their first message. Fire-and-forget: never surfaces an error to the
    caller, since a cold RunPod worker legitimately takes ~2 minutes here."""
    try:
        await _proxy_body("/warm", {})
    except Exception:
        pass
    return {"status": "ok"}


@gateway.get("/ping")
def ping():
    return "OK"


@gateway.get("/llms.txt", response_class=PlainTextResponse)
def llms_txt():
    return (_STATIC / "llms.txt").read_text()


@gateway.get("/.well-known/x402")
def well_known_x402():
    return json.loads((_STATIC / "x402.json").read_text())


@gateway.get("/.well-known/mcp-registry-auth", response_class=PlainTextResponse)
def mcp_registry_auth():
    return "v=MCPv1; k=ed25519; p=+w+csrLiNQXqnyFzhqGmVXkNDkn6jrOTW0gfPvNWRsc="


# ── Paid endpoints ─────────────────────────────────────────────────────────

@gateway.post("/agent")
async def agent(request: Request):
    return await _proxy_body("/agent", await request.json())


@gateway.post("/ask")
async def ask(request: Request):
    return await _proxy_body("/ask", await request.json())


@gateway.post("/due-diligence")
async def due_diligence(request: Request):
    return await _proxy_params("/due-diligence", dict(request.query_params))


@gateway.post("/sec")
async def sec(request: Request):
    return await _proxy_params("/sec", dict(request.query_params))


@gateway.post("/kelly")
async def kelly(request: Request):
    return await _proxy_params("/kelly", dict(request.query_params))


# ── Web frontend endpoint (MoR-subscription gated, not x402) ───────────────
# Deliberately excluded from _ROUTES so the x402 middleware never intercepts it.

@gateway.post("/web/agent")
async def web_agent(request: Request):
    if not WEB_SHARED_SECRET or request.headers.get("x-web-secret") != WEB_SHARED_SECRET:
        raise HTTPException(status_code=401, detail="unauthorized")
    if _web_agent_rate_limited(_client_ip(request)):
        raise HTTPException(status_code=429, detail="rate limit exceeded — try again later")
    return await _proxy_body("/agent", await request.json())


if __name__ == "__main__":
    uvicorn.run("gateway:gateway", host="0.0.0.0", port=8080, reload=False)
