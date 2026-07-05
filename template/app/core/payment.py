"""Payment middleware for Finance AI Agent — two-mode verification.

Mode A — x402 Authorization (fast, used by x402-compatible clients):
  Client signs an EIP-3009 USDC authorization → sends in X-Payment header.
  Facilitator (x402.org) verifies signature + settles on Base atomically.

Mode B — Direct RPC Tx Verification (pre-payment, funds confirmed first):
  Client sends a real USDC transfer on Base → gets tx hash.
  Sends tx hash in X-Payment header (starts with "0x").
  Server verifies on-chain via Base RPC BEFORE serving the request:
    • transaction is confirmed (status == 1)
    • recipient == RECEIVER_WALLET
    • amount >= PAYMENT_AMOUNT_USDC (in 6-decimal units)
    • tx hash not already used (replay protection)

Header routing:
  X-Payment: 0x<64-char-hex>          → Mode B (direct RPC check)
  X-Payment: <base64-json-payload>    → Mode A (x402 authorization)

Spec: https://x402.org
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import httpx
import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = structlog.get_logger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
PAYMENT_REQUIRED: bool = os.getenv("PAYMENT_REQUIRED", "true").lower() == "true"
RECEIVER_WALLET: str = os.getenv(
    "RECEIVER_WALLET_ADDRESS",
    "0x0000000000000000000000000000000000000000",
).lower()
PAYMENT_AMOUNT_USD: str = os.getenv("PAYMENT_AMOUNT_USDC", "0.05")
PAYMENT_AMOUNT_UNITS: int = int(float(PAYMENT_AMOUNT_USD) * 1_000_000)  # 6 decimals

# Base mainnet by default; set BASE_NETWORK=eip155:84532 for Sepolia testnet
BASE_NETWORK: str = os.getenv("BASE_NETWORK", "eip155:8453")
FACILITATOR_URL: str = os.getenv("X402_FACILITATOR_URL", "https://x402.org/facilitator")

# Base RPC endpoints
_BASE_RPC: dict[str, str] = {
    "eip155:8453": os.getenv("BASE_RPC_URL", "https://mainnet.base.org"),
    "eip155:84532": os.getenv("BASE_SEPOLIA_RPC_URL", "https://sepolia.base.org"),
}

# USDC contract addresses
_USDC_ADDRESS: dict[str, str] = {
    "eip155:8453": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
    "eip155:84532": "0x036cbd53842c5426634e7929541ec2318f3dcf7e",
}

# ERC-20 Transfer event topic
_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# Replay-attack protection: tx hashes that have already been used
_used_tx_hashes: set[str] = set()
_used_tx_lock = asyncio.Lock()

# Routes that require payment
_PAID_ROUTES: set[tuple[str, str]] = {
    ("POST", "/api/v1/chatbot/chat"),
    ("POST", "/api/v1/chatbot/chat/stream"),
}


# ── Mode B: Direct RPC verification ──────────────────────────────────────────

def _is_tx_hash(value: str) -> bool:
    """Return True if value looks like a 0x-prefixed 32-byte hex hash."""
    return bool(value and value.startswith("0x") and len(value) == 66 and
                all(c in "0123456789abcdefABCDEF" for c in value[2:]))


async def _verify_tx_onchain(tx_hash: str) -> tuple[bool, str]:
    """Verify a USDC transfer tx on Base before serving the request.

    Returns (ok, reason) where ok=True means payment is valid.
    Checks (in order):
      1. tx exists and is confirmed (status == 1)
      2. not already used (replay protection)
      3. has a USDC Transfer log to RECEIVER_WALLET
      4. transferred amount >= PAYMENT_AMOUNT_UNITS
    """
    rpc_url = _BASE_RPC.get(BASE_NETWORK, "https://mainnet.base.org")
    usdc_addr = _USDC_ADDRESS.get(BASE_NETWORK, _USDC_ADDRESS["eip155:8453"])
    tx_lower = tx_hash.lower()

    # Replay check (fast, no RPC call needed)
    async with _used_tx_lock:
        if tx_lower in _used_tx_hashes:
            return False, "tx_already_used"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "method": "eth_getTransactionReceipt",
                    "params": [tx_hash],
                    "id": 1,
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.exception("rpc_call_failed", error=str(exc), rpc=rpc_url)
        return False, f"rpc_error: {exc}"

    receipt = data.get("result")
    if not receipt:
        return False, "tx_not_found"

    # Must be confirmed (status 0x1)
    if receipt.get("status") != "0x1":
        return False, "tx_failed_or_pending"

    # Scan logs for USDC Transfer to our wallet
    logs = receipt.get("logs", [])
    receiver_padded = "0x" + "0" * 24 + RECEIVER_WALLET[2:].lower()

    for log in logs:
        topics = [t.lower() for t in log.get("topics", [])]
        contract = log.get("address", "").lower()

        if contract != usdc_addr:
            continue
        if len(topics) < 3:
            continue
        if topics[0] != _TRANSFER_TOPIC:
            continue
        if topics[2] != receiver_padded:
            continue

        # Decode amount from log data (big-endian uint256)
        raw_data = log.get("data", "0x")
        amount = int(raw_data, 16) if raw_data and raw_data != "0x" else 0

        if amount < PAYMENT_AMOUNT_UNITS:
            return False, f"insufficient_amount: got {amount}, need {PAYMENT_AMOUNT_UNITS}"

        # All checks passed — mark tx as used
        async with _used_tx_lock:
            _used_tx_hashes.add(tx_lower)

        logger.info(
            "rpc_payment_verified",
            tx_hash=tx_hash,
            amount_usdc=amount / 1_000_000,
            receiver=RECEIVER_WALLET[:10] + "...",
        )
        return True, "ok"

    return False, "no_usdc_transfer_to_receiver"


# ── Mode A: x402 authorization middleware ────────────────────────────────────

def _build_x402_middleware() -> Callable[[Request, Callable], Awaitable[Response]]:
    """Build x402 SDK middleware (EIP-3009 authorization path)."""
    try:
        from x402.http.facilitator_client import HTTPFacilitatorClient
        from x402.http.middleware.fastapi import payment_middleware_from_config
        from x402.mechanisms.evm.exact.server import ExactEvmScheme
    except ImportError:
        logger.warning("x402_not_installed_payment_disabled")

        async def _noop_mw(request: Request, call_next: Callable) -> Response:
            return await call_next(request)

        return _noop_mw

    facilitator = HTTPFacilitatorClient({"url": FACILITATOR_URL})
    schemes = [{"network": BASE_NETWORK, "server": ExactEvmScheme()}]
    routes = {
        "POST /api/v1/chatbot/chat": {
            "accepts": {"scheme": "exact", "network": BASE_NETWORK,
                        "payTo": RECEIVER_WALLET, "price": f"${PAYMENT_AMOUNT_USD}"}
        },
        "POST /api/v1/chatbot/chat/stream": {
            "accepts": {"scheme": "exact", "network": BASE_NETWORK,
                        "payTo": RECEIVER_WALLET, "price": f"${PAYMENT_AMOUNT_USD}"}
        },
    }
    logger.info(
        "x402_middleware_initialized",
        network=BASE_NETWORK,
        receiver=RECEIVER_WALLET[:10] + "...",
        price_usd=PAYMENT_AMOUNT_USD,
        facilitator=FACILITATOR_URL,
    )
    return payment_middleware_from_config(
        routes=routes,
        facilitator_client=facilitator,
        schemes=schemes,
        sync_facilitator_on_start=True,
    )


# ── Combined middleware ───────────────────────────────────────────────────────

def attach_payment_middleware(app: "FastAPI") -> None:
    """Attach payment middleware to the FastAPI app.

    Routes requests to Mode A (x402) or Mode B (direct RPC) based on
    the X-Payment header format. PAYMENT_REQUIRED=false bypasses both.
    """
    if not PAYMENT_REQUIRED:
        logger.info("payment_middleware_disabled", reason="PAYMENT_REQUIRED=false")

        @app.middleware("http")
        async def _noop(request: Request, call_next: Callable) -> Response:
            return await call_next(request)

        return

    x402_mw = _build_x402_middleware()

    @app.middleware("http")
    async def _payment(request: Request, call_next: Callable) -> Response:
        method, path = request.method, request.url.path

        if (method, path) not in _PAID_ROUTES:
            return await call_next(request)

        x_payment = request.headers.get("x-payment") or request.headers.get("X-Payment", "")

        if not x_payment:
            return JSONResponse(status_code=402, content=build_402_challenge(path))

        # ── Mode B: tx hash → verify on-chain BEFORE serving ─────────────────
        if _is_tx_hash(x_payment):
            ok, reason = await _verify_tx_onchain(x_payment)
            if not ok:
                logger.warning("rpc_payment_rejected", tx=x_payment, reason=reason)
                return JSONResponse(
                    status_code=402,
                    content={
                        "error": "Payment verification failed",
                        "reason": reason,
                        "hint": (
                            "Send a confirmed USDC transfer to "
                            f"{RECEIVER_WALLET} on {BASE_NETWORK} "
                            f"(≥ {PAYMENT_AMOUNT_USD} USDC) then pass the tx hash."
                        ),
                    },
                )
            # Funds confirmed on-chain — serve the request
            response = await call_next(request)
            response.headers["X-Payment-Verified"] = "rpc"
            response.headers["X-Payment-Tx"] = x_payment
            return response

        # ── Mode A: x402 authorization → facilitator verify + settle ─────────
        try:
            return await x402_mw(request, call_next)
        except Exception as exc:
            logger.exception("x402_middleware_error", error=str(exc))
            return JSONResponse(
                status_code=500,
                content={"error": "Payment verification failed", "detail": str(exc)},
            )


# ── Helpers ───────────────────────────────────────────────────────────────────

def build_402_challenge(resource: str) -> dict:
    """Return a standards-compliant 402 challenge dict."""
    return {
        "x402Version": 1,
        "error": "Payment required to access this resource.",
        "accepts": [
            {
                "scheme": "exact",
                "network": BASE_NETWORK,
                "maxAmountRequired": str(PAYMENT_AMOUNT_UNITS),
                "resource": resource,
                "description": f"Finance AI Agent inference — ${PAYMENT_AMOUNT_USD} USDC per call",
                "mimeType": "application/json",
                "payTo": RECEIVER_WALLET,
                "maxTimeoutSeconds": 300,
                "asset": _USDC_ADDRESS.get(BASE_NETWORK, _USDC_ADDRESS["eip155:8453"]),
                "extra": {"name": "USD Coin", "version": "2"},
            }
        ],
        "modes": {
            "x402": "Send EIP-3009 signed authorization in X-Payment header",
            "rpc": "Send confirmed USDC tx hash (0x...) in X-Payment header",
        },
    }
