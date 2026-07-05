"""
x402 Payment Flow Test
Demonstrates the full payment gate lifecycle:
  1. Request without payment  → 402 + challenge JSON
  2. Request with invalid token → 402
  3. Request with valid mock token → 200 + agent response

Usage:
    # With payment gate DISABLED (default dev mode):
    python test_payment_flow.py

    # With payment gate ENABLED:
    # Set PAYMENT_REQUIRED=true in .env.development, restart container, then:
    python test_payment_flow.py
"""

import json
import sys

import httpx

BASE_URL = "http://localhost:8000"
TEST_EMAIL = "test_kelly@finance-agent.dev"
TEST_PASSWORD = "KellyTest123!"

CHAT_ENDPOINT = f"{BASE_URL}/api/v1/chatbot/chat"
TEST_MESSAGE = "What is 2 + 2? Keep your answer to one sentence."


def login(client: httpx.Client) -> str:
    resp = client.post(
        f"{BASE_URL}/api/v1/auth/login",
        data={"email": TEST_EMAIL, "password": TEST_PASSWORD, "grant_type": "password"},
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def create_session(client: httpx.Client, user_token: str) -> str:
    resp = client.post(
        f"{BASE_URL}/api/v1/auth/session",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    resp.raise_for_status()
    return resp.json()["token"]["access_token"]


def generate_mock_token() -> str:
    """Generate a valid mock payment token by calling the helper."""
    import hmac
    import hashlib
    import time
    import os

    secret = os.getenv("PAYMENT_SECRET", "dev-payment-secret-change-in-prod")
    receiver = os.getenv("RECEIVER_WALLET_ADDRESS", "0x0000000000000000000000000000000000000000")
    amount_usdc = float(os.getenv("PAYMENT_AMOUNT_USDC", "0.05"))
    units = int(amount_usdc * 1_000_000)
    resource = "/api/v1/chatbot/chat"

    ts = int(time.time())
    sig = hmac.new(
        secret.encode(),
        f"{ts}:{resource}:{units}:{receiver}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"mock_pay_{ts}_{sig}"


def print_separator(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


def test_no_payment(session_token: str):
    """Test 1: Request without any payment header."""
    print_separator("Test 1: No X-Payment header")

    resp = httpx.post(
        CHAT_ENDPOINT,
        headers={"Authorization": f"Bearer {session_token}"},
        json={"messages": [{"role": "user", "content": TEST_MESSAGE}]},
        timeout=10.0,
    )

    if resp.status_code == 402:
        # FastAPI wraps HTTPException detail in {"detail": ...}
        # detail may be a dict or a JSON-encoded string depending on FastAPI version
        raw_detail = resp.json().get("detail", resp.json())
        challenge = json.loads(raw_detail) if isinstance(raw_detail, str) else raw_detail
        print(f"[PASS] Got HTTP 402 as expected")
        print(f"\nPayment Challenge:")
        print(f"  x402Version: {challenge.get('x402Version')}")
        print(f"  error:       {challenge.get('error')}")
        accepts = challenge.get("accepts", [{}])[0]
        print(f"\n  Payment Details:")
        print(f"    network:    {accepts.get('network')}")
        asset = accepts.get('asset', '')
        print(f"    asset:      {asset[:20]}..." if asset else "    asset:      N/A")
        print(f"    payTo:      {accepts.get('payTo')}")
        amount = int(accepts.get("maxAmountRequired", 0)) / 1_000_000
        print(f"    amount:     ${amount:.2f} USDC")
        print(f"    resource:   {accepts.get('resource')}")
        print(f"    expires in: {accepts.get('maxTimeoutSeconds')}s")
    elif resp.status_code == 200:
        print(f"[INFO] Payment gate is DISABLED (PAYMENT_REQUIRED=false)")
        print(f"       Got 200 OK — agent responded without payment.")
        print(f"       To test 402 flow: set PAYMENT_REQUIRED=true in .env.development")
    else:
        print(f"[FAIL] Unexpected status: {resp.status_code}")
        print(resp.text[:300])


def test_invalid_payment(session_token: str):
    """Test 2: Request with an invalid/expired token."""
    print_separator("Test 2: Invalid X-Payment token")

    resp = httpx.post(
        CHAT_ENDPOINT,
        headers={
            "Authorization": f"Bearer {session_token}",
            "X-Payment": "invalid_token_12345",
        },
        json={"messages": [{"role": "user", "content": TEST_MESSAGE}]},
        timeout=10.0,
    )

    if resp.status_code == 402:
        print(f"[PASS] Got HTTP 402 — invalid token correctly rejected")
    elif resp.status_code == 200:
        print(f"[INFO] Payment gate is DISABLED — token not checked")
    else:
        print(f"[FAIL] Unexpected status: {resp.status_code}")


def test_valid_mock_payment(session_token: str):
    """Test 3: Request with a valid mock payment token."""
    print_separator("Test 3: Valid mock X-Payment token")

    token = generate_mock_token()
    print(f"Generated mock token: {token[:40]}...")

    resp = httpx.post(
        CHAT_ENDPOINT,
        headers={
            "Authorization": f"Bearer {session_token}",
            "X-Payment": token,
        },
        json={"messages": [{"role": "user", "content": TEST_MESSAGE}]},
        timeout=60.0,
    )

    if resp.status_code == 200:
        messages = resp.json().get("messages", [])
        answer = next((m["content"] for m in reversed(messages) if m["role"] == "assistant"), "")
        print(f"[PASS] Got HTTP 200 — payment accepted, agent responded:")
        print(f"       \"{answer}\"")
    elif resp.status_code == 402:
        print(f"[INFO] Got 402 — payment gate is active but mock token rejected")
        print(f"       Make sure PAYMENT_REQUIRED=true and container is restarted with 'docker compose up -d'")
    else:
        print(f"[FAIL] Unexpected status: {resp.status_code}")
        print(resp.text[:300])


def test_simple_mock_payment(session_token: str):
    """Test 4: Simple mock_pay_ prefix token (dev shortcut)."""
    print_separator("Test 4: Simple mock_pay_ prefix token")

    token = "mock_pay_test_dev_token"
    resp = httpx.post(
        CHAT_ENDPOINT,
        headers={
            "Authorization": f"Bearer {session_token}",
            "X-Payment": token,
        },
        json={"messages": [{"role": "user", "content": TEST_MESSAGE}]},
        timeout=60.0,
    )

    if resp.status_code == 200:
        print(f"[PASS] Got HTTP 200 — simple mock token accepted in dev mode")
    elif resp.status_code == 402:
        print(f"[INFO] Got 402 — either PAYMENT_REQUIRED=false or gate active")
    else:
        print(f"[FAIL] Unexpected status: {resp.status_code}")


def main():
    print("\n" + "=" * 60)
    print("  Finance AI Agent — x402 Payment Flow Test")
    print("=" * 60)

    # Check payment gate status
    import os
    gate_enabled = os.getenv("PAYMENT_REQUIRED", "false").lower() == "true"
    print(f"\nPayment gate (local env): {'ENABLED' if gate_enabled else 'DISABLED'}")
    print("Note: container reads its own .env.development — run 'docker compose up -d' after changes\n")

    with httpx.Client(timeout=30.0) as client:
        health = client.get(f"{BASE_URL}/health")
        if health.status_code != 200:
            print("[ERR] API not healthy — start containers first")
            sys.exit(1)
        print("[OK] API healthy")

        user_token = login(client)
        print("[OK] Logged in")

        session_token = create_session(client, user_token)
        print("[OK] Session created")

    test_no_payment(session_token)
    test_invalid_payment(session_token)
    test_valid_mock_payment(session_token)
    test_simple_mock_payment(session_token)

    print(f"\n{'=' * 60}")
    print("  Summary")
    print("=" * 60)
    print("""
To enable the payment gate:
  1. Edit template/.env.development:
       PAYMENT_REQUIRED=true
       RECEIVER_WALLET_ADDRESS=0xYOUR_REAL_WALLET

  2. Restart container (MUST use 'up -d', not 'restart'):
       docker compose --env-file .env.development up -d app

  3. Re-run this script — Tests 1 and 2 will return 402,
     Test 3 will pass with a valid signed token.

For production (Base mainnet):
  - Replace _verify_signed_token() in app/core/payment.py
    with on-chain verification via the x402 facilitator:
    https://x402.org/facilitator
  - Set RECEIVER_WALLET_ADDRESS to your real Base wallet
  - Clients pay 0.05 USDC per call, settled on-chain
""")


if __name__ == "__main__":
    main()
