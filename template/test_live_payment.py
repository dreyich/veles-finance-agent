"""
test_live_payment.py — Full x402 USDC Payment Flow Demo
========================================================

Demonstrates the complete real payment flow:
  1. Hit /chat without payment → 402 challenge
  2. Decode the challenge (payment requirements)
  3. Sign an EIP-3009 USDC transfer authorization
  4. Build the X-Payment header
  5. Retry with X-Payment → success + tx hash
  6. Show USDC balance before and after

Requirements:
  - Server running: make dev  (or docker-compose up)
  - PAYER_PRIVATE_KEY env var (Base wallet with ≥ $0.10 USDC for two test calls)
  - Optional: BASE_RPC_URL (defaults to Coinbase's public Base RPC)

Setup (get test USDC on Base Sepolia):
  1. Set BASE_NETWORK=eip155:84532 in .env.development
  2. Get test ETH from https://faucet.quicknode.com/base/sepolia
  3. Get test USDC from https://faucet.circle.com

Usage:
    # Testnet (safe, free)
    $env:PAYER_PRIVATE_KEY="0xYOUR_PRIVATE_KEY"
    $env:BASE_NETWORK="eip155:84532"
    python test_live_payment.py

    # Mainnet (real $0.05 USDC)
    $env:PAYER_PRIVATE_KEY="0xYOUR_PRIVATE_KEY"
    python test_live_payment.py
"""

import json
import os
import sys
import time

import httpx

BASE_URL = "http://localhost:8000"
TEST_EMAIL = "payment_test@finance-agent.dev"
TEST_PASSWORD = "PayTest2024!"
TEST_USERNAME = "payment_tester"

PAYER_PRIVATE_KEY: str = os.getenv("PAYER_PRIVATE_KEY", "")
BASE_NETWORK: str = os.getenv("BASE_NETWORK", "eip155:8453")
BASE_RPC_URL: str = os.getenv(
    "BASE_RPC_URL",
    "https://mainnet.base.org" if BASE_NETWORK == "eip155:8453" else "https://sepolia.base.org",
)

# USDC contract addresses
USDC_ADDRESS = {
    "eip155:8453": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",   # Base mainnet
    "eip155:84532": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",  # Base Sepolia
}

NETWORK_NAMES = {
    "eip155:8453": "Base Mainnet",
    "eip155:84532": "Base Sepolia (Testnet)",
}

USDC_ABI_BALANCE = [
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
        "stateMutability": "view",
    }
]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _separator(title: str = "") -> None:
    if title:
        pad = (58 - len(title)) // 2
        print("\n" + "─" * pad + f" {title} " + "─" * pad)
    else:
        print("\n" + "─" * 60)


def _check_deps() -> bool:
    """Check that eth-account and web3 are available."""
    missing = []
    for pkg in ("eth_account", "web3"):
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"[ERR] Missing packages: {', '.join(missing)}")
        print("      Run: uv add 'x402[evm]' eth-account web3")
        return False
    return True


def _get_usdc_balance(wallet: str, network: str) -> float:
    """Return USDC balance in human-readable units (6 decimals)."""
    try:
        from web3 import Web3

        w3 = Web3(Web3.HTTPProvider(BASE_RPC_URL))
        usdc_addr = USDC_ADDRESS.get(network, USDC_ADDRESS["eip155:8453"])
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(usdc_addr),
            abi=USDC_ABI_BALANCE,
        )
        raw = contract.functions.balanceOf(Web3.to_checksum_address(wallet)).call()
        return raw / 1_000_000
    except Exception as exc:
        print(f"[WARN] Could not fetch USDC balance: {exc}")
        return -1.0


def _build_payment_header(requirements: dict, private_key: str, network: str) -> str:
    """Sign an EIP-3009 USDC authorization and return the X-Payment header value."""
    import secrets

    from eth_account import Account
    from eth_account.messages import encode_typed_data
    from web3 import Web3

    account = Account.from_key(private_key)
    payer_address = account.address

    usdc_addr = USDC_ADDRESS.get(network, USDC_ADDRESS["eip155:8453"])
    chain_id = int(network.split(":")[-1])

    amount_raw = int(requirements["maxAmountRequired"])
    receiver = requirements["payTo"]
    nonce = "0x" + secrets.token_hex(32)
    valid_after = 0
    valid_before = int(time.time()) + 300  # 5-minute window

    # EIP-712 typed data for USDC EIP-3009
    typed_data = {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "TransferWithAuthorization": [
                {"name": "from", "type": "address"},
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "validAfter", "type": "uint256"},
                {"name": "validBefore", "type": "uint256"},
                {"name": "nonce", "type": "bytes32"},
            ],
        },
        "primaryType": "TransferWithAuthorization",
        "domain": {
            "name": "USD Coin",
            "version": "2",
            "chainId": chain_id,
            "verifyingContract": Web3.to_checksum_address(usdc_addr),
        },
        "message": {
            "from": Web3.to_checksum_address(payer_address),
            "to": Web3.to_checksum_address(receiver),
            "value": amount_raw,
            "validAfter": valid_after,
            "validBefore": valid_before,
            "nonce": bytes.fromhex(nonce[2:]),
        },
    }

    signed = account.sign_typed_data(
        domain_data=typed_data["domain"],
        message_types={"TransferWithAuthorization": typed_data["types"]["TransferWithAuthorization"]},
        message_data=typed_data["message"],
    )

    # x402 exact scheme payload
    payload = {
        "x402Version": 1,
        "scheme": "exact",
        "network": network,
        "payload": {
            "signature": signed.signature.hex()
            if isinstance(signed.signature, bytes)
            else signed.signature,
            "authorization": {
                "from": payer_address,
                "to": receiver,
                "value": str(amount_raw),
                "validAfter": str(valid_after),
                "validBefore": str(valid_before),
                "nonce": nonce,
            },
        },
    }

    import base64

    return base64.b64encode(json.dumps(payload).encode()).decode()


# ─── Auth ─────────────────────────────────────────────────────────────────────

def _auth_flow(client: httpx.Client) -> str:
    """Register + login + create session. Returns session token."""
    client.post(
        f"{BASE_URL}/api/v1/auth/register",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD, "username": TEST_USERNAME},
    )
    r = client.post(
        f"{BASE_URL}/api/v1/auth/login",
        data={"email": TEST_EMAIL, "password": TEST_PASSWORD, "grant_type": "password"},
    )
    r.raise_for_status()
    user_token = r.json()["access_token"]

    r2 = client.post(
        f"{BASE_URL}/api/v1/auth/session",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    r2.raise_for_status()
    return r2.json()["token"]["access_token"]


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print("\n" + "═" * 60)
    print("  Finance AI Agent — x402 Live Payment Flow")
    print(f"  Network: {NETWORK_NAMES.get(BASE_NETWORK, BASE_NETWORK)}")
    print("═" * 60)

    # 1. Check dependencies
    if not _check_deps():
        sys.exit(1)

    has_wallet = bool(PAYER_PRIVATE_KEY)
    if not has_wallet:
        print(
            "\n[WARN] PAYER_PRIVATE_KEY not set — will show flow up to signing step.\n"
            "       Set it to make a real on-chain payment:\n"
            "       $env:PAYER_PRIVATE_KEY='0xYOUR_KEY'\n"
        )
    else:
        from eth_account import Account

        account = Account.from_key(PAYER_PRIVATE_KEY)
        print(f"\n  Payer wallet: {account.address}")

    # 2. Health check
    _separator("Step 1 — Health Check")
    with httpx.Client(timeout=10.0) as c:
        try:
            h = c.get(f"{BASE_URL}/health")
            print(f"[OK] API: {h.json()['status']}")
        except Exception:
            print("[ERR] API not reachable. Run 'make dev' or 'docker-compose up'.")
            sys.exit(1)

    with httpx.Client(timeout=30.0) as client:
        # 3. Auth
        _separator("Step 2 — Authentication")
        session_token = _auth_flow(client)
        print(f"[OK] Session token obtained: {session_token[:20]}...")

        headers_base = {
            "Authorization": f"Bearer {session_token}",
            "Content-Type": "application/json",
        }
        payload_body = json.dumps({"messages": [{"role": "user", "content": "What is 2+2?"}]})

        # 4. Trigger 402
        _separator("Step 3 — Trigger 402 Challenge (no payment)")
        r = client.post(
            f"{BASE_URL}/api/v1/chatbot/chat",
            headers=headers_base,
            content=payload_body,
        )
        if r.status_code != 402:
            print(f"[WARN] Expected 402, got {r.status_code}.")
            if r.status_code == 200:
                print("       PAYMENT_REQUIRED may be false — set it to 'true' in .env.development")
            else:
                print(f"       Response: {r.text[:300]}")
            sys.exit(0)

        challenge = r.json()
        print(f"[OK] 402 received. x402Version: {challenge.get('x402Version')}")

        accepts = challenge.get("accepts", [{}])[0]
        print(f"\n  Payment Requirements:")
        print(f"    Network:  {accepts.get('network')}")
        print(f"    Receiver: {accepts.get('payTo')}")
        print(f"    Amount:   {int(accepts.get('maxAmountRequired', 0)) / 1_000_000:.6f} USDC")
        print(f"    Asset:    {accepts.get('asset')}")

        if not has_wallet:
            _separator("Skipped — No wallet configured")
            print("  To complete the flow, set PAYER_PRIVATE_KEY and re-run.\n")
            return

        from eth_account import Account

        account = Account.from_key(PAYER_PRIVATE_KEY)

        # 5. Check balance before
        _separator("Step 4 — USDC Balance Before")
        balance_before = _get_usdc_balance(account.address, BASE_NETWORK)
        if balance_before >= 0:
            print(f"[OK] Balance: {balance_before:.6f} USDC")
            required = int(accepts.get("maxAmountRequired", 0)) / 1_000_000
            if balance_before < required:
                print(f"[ERR] Insufficient USDC. Need {required:.6f}, have {balance_before:.6f}.")
                print(
                    "      Get test USDC from:\n"
                    "        Base Sepolia: https://faucet.circle.com\n"
                    "        Base Mainnet: Coinbase / Uniswap"
                )
                sys.exit(1)

        # 6. Sign payment
        _separator("Step 5 — Sign EIP-3009 Authorization")
        print("  Building signed USDC transfer authorization...")
        x_payment = _build_payment_header(accepts, PAYER_PRIVATE_KEY, BASE_NETWORK)
        print(f"[OK] X-Payment header built ({len(x_payment)} chars)")
        print(f"     Preview: {x_payment[:60]}...")

        # 7. Retry with payment
        _separator("Step 6 — Send Payment + Request")
        print("  Sending request with X-Payment header...")
        t0 = time.time()
        r2 = client.post(
            f"{BASE_URL}/api/v1/chatbot/chat",
            headers={**headers_base, "X-Payment": x_payment},
            content=payload_body,
            timeout=60.0,
        )
        elapsed = time.time() - t0

        if r2.status_code == 200:
            print(f"[OK] Request succeeded in {elapsed:.1f}s")

            tx_hash = r2.headers.get("x-payment-response") or r2.headers.get("X-Payment-Response")
            if tx_hash:
                explorer = (
                    "https://basescan.org/tx/"
                    if BASE_NETWORK == "eip155:8453"
                    else "https://sepolia.basescan.org/tx/"
                )
                print(f"\n  ✓ Transaction settled on-chain!")
                print(f"    Tx Hash:  {tx_hash}")
                print(f"    Explorer: {explorer}{tx_hash}")
            else:
                print("  (No X-Payment-Response header — check facilitator logs)")

            data = r2.json()
            for msg in reversed(data.get("messages", [])):
                if msg["role"] == "assistant":
                    print(f"\n  Agent response: {msg['content'][:100]}...")
                    break
        elif r2.status_code == 402:
            err = r2.json()
            print(f"[ERR] Payment rejected by facilitator.")
            print(f"      Detail: {json.dumps(err, indent=2)[:300]}")
        else:
            print(f"[ERR] Unexpected status {r2.status_code}: {r2.text[:300]}")
            sys.exit(1)

        # 8. Balance after
        _separator("Step 7 — USDC Balance After")
        balance_after = _get_usdc_balance(account.address, BASE_NETWORK)
        if balance_before >= 0 and balance_after >= 0:
            spent = balance_before - balance_after
            print(f"[OK] Balance after:  {balance_after:.6f} USDC")
            print(f"     Spent:          {spent:.6f} USDC  (${spent:.4f})")
            if abs(spent - 0.05) < 0.001:
                print("     ✓ Exactly $0.05 deducted — payment confirmed!")
            else:
                print(f"     [WARN] Expected $0.05, spent ${spent:.4f}")

    _separator()
    print("  Flow complete.\n")


if __name__ == "__main__":
    main()
