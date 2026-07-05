"""
Test script: asks the Finance AI Agent to analyse NVDA using the
get_market_data tool and prints the full response.

Usage:
    python test_market_data.py

Requirements:
    Server running: make dev  (or docker-compose up)
"""

import sys

import httpx

BASE_URL = "http://localhost:8000"
TEST_EMAIL = "test_marketdata@finance-agent.dev"
TEST_PASSWORD = "MarketData123!"
TEST_USERNAME = "market_tester"


def register_user(client: httpx.Client) -> None:
    resp = client.post(
        f"{BASE_URL}/api/v1/auth/register",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD, "username": TEST_USERNAME},
    )
    if resp.status_code == 200:
        print("[OK] Registered user:", TEST_EMAIL)
    elif resp.status_code in (400, 409):
        print("[OK] User already exists, proceeding to login.")
    else:
        resp.raise_for_status()


def login_user(client: httpx.Client) -> str:
    resp = client.post(
        f"{BASE_URL}/api/v1/auth/login",
        data={"email": TEST_EMAIL, "password": TEST_PASSWORD, "grant_type": "password"},
    )
    resp.raise_for_status()
    print("[OK] Logged in, got user token.")
    return resp.json()["access_token"]


def create_session(client: httpx.Client, user_token: str) -> str:
    resp = client.post(
        f"{BASE_URL}/api/v1/auth/session",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    resp.raise_for_status()
    print("[OK] Session created.")
    return resp.json()["token"]["access_token"]


def chat(client: httpx.Client, session_token: str, message: str) -> str:
    resp = client.post(
        f"{BASE_URL}/api/v1/chatbot/chat",
        headers={
            "Authorization": f"Bearer {session_token}",
            "Content-Type": "application/json",
        },
        json={"messages": [{"role": "user", "content": message}]},
        timeout=90.0,
    )
    resp.raise_for_status()
    for msg in reversed(resp.json()["messages"]):
        if msg["role"] == "assistant":
            return msg["content"]
    return "(no assistant response found)"


def _standalone_tool_check(ticker: str = "NVDA") -> None:
    """Quick sanity-check: call get_market_data directly without the API."""
    print("\n" + "=" * 60)
    print("  Standalone tool check (no API required)")
    print("=" * 60)

    try:
        from app.core.langgraph.tools.market_data_tools import get_market_data

        result = get_market_data.invoke({"ticker": ticker})
        print(result)
        print("\n[OK] Standalone tool call succeeded.\n")
    except Exception as exc:
        print(f"[ERR] Standalone tool call failed: {exc}")


def main() -> None:
    question = (
        "Please use the get_market_data tool to fetch a full market snapshot "
        "for NVDA (NVIDIA Corporation). Then give me a brief analyst-style "
        "summary: is the stock expensive vs its sector, what does the news say, "
        "and what is the analyst consensus?"
    )

    # 1. Standalone check (works even if the server is not running)
    _standalone_tool_check("NVDA")

    # 2. Full agent round-trip via the API
    print("=" * 60)
    print("  Finance AI Agent — Market Data Test (NVDA)")
    print("=" * 60 + "\n")

    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        try:
            health = client.get("/health")
        except httpx.ConnectError:
            print(
                "[SKIP] API server is not running — skipping full agent test.\n"
                "       Run 'make dev' or 'docker-compose up' to start it."
            )
            sys.exit(0)

        if health.status_code != 200:
            print("[ERR] API is not healthy. Make sure Docker containers are running.")
            sys.exit(1)
        print(f"[OK] API healthy: {health.json()['status']}\n")

        register_user(client)
        user_token = login_user(client)
        session_token = create_session(client, user_token)

        print(f"Question:\n  {question}\n")
        print("Waiting for agent response...\n")
        answer = chat(client, session_token, question)

    print("-" * 60)
    print("Agent Response:")
    print("-" * 60)
    print(answer)
    print("-" * 60 + "\n")


if __name__ == "__main__":
    main()
