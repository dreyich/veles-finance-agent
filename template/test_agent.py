"""
Test script: sends a Kelly Criterion question to the Finance AI Agent
and prints the full response.

Usage:
    python test_agent.py

Requirements:
    pip install httpx   (already in the project venv)
"""

import httpx
import json
import sys

BASE_URL = "http://localhost:8000"
TEST_EMAIL = "test_kelly@finance-agent.dev"
TEST_PASSWORD = "KellyTest123!"
TEST_USERNAME = "kelly_tester"


def register_user(client: httpx.Client) -> dict:
    """Register a new test user (idempotent — ignores 'already exists' errors)."""
    resp = client.post(
        f"{BASE_URL}/api/v1/auth/register",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD, "username": TEST_USERNAME},
    )
    if resp.status_code == 200:
        data = resp.json()
        print(f"[OK] Registered user: {TEST_EMAIL}")
        return data
    if resp.status_code in (400, 409):
        print(f"[OK] User already exists, proceeding to login.")
        return {}
    resp.raise_for_status()


def login_user(client: httpx.Client) -> str:
    """Log in and return the user-level JWT token."""
    resp = client.post(
        f"{BASE_URL}/api/v1/auth/login",
        data={"email": TEST_EMAIL, "password": TEST_PASSWORD, "grant_type": "password"},
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]
    print(f"[OK] Logged in, got user token.")
    return token


def create_session(client: httpx.Client, user_token: str) -> str:
    """Create a chat session and return the session-scoped JWT token."""
    resp = client.post(
        f"{BASE_URL}/api/v1/auth/session",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    resp.raise_for_status()
    session_token = resp.json()["token"]["access_token"]
    print(f"[OK] Session created.")
    return session_token


def chat(client: httpx.Client, session_token: str, message: str) -> str:
    """Send a chat message and return the agent's text response."""
    resp = client.post(
        f"{BASE_URL}/api/v1/chatbot/chat",
        headers={
            "Authorization": f"Bearer {session_token}",
            "Content-Type": "application/json",
        },
        json={"messages": [{"role": "user", "content": message}]},
        timeout=60.0,
    )
    resp.raise_for_status()
    messages = resp.json()["messages"]
    # Return the last assistant message
    for msg in reversed(messages):
        if msg["role"] == "assistant":
            return msg["content"]
    return "(no assistant response found)"


def main():
    question = (
        "I have a trading strategy with a 60% win rate and a 2.0 payout ratio. "
        "Calculate my optimal position size using the Kelly Criterion tool."
    )

    print("\n" + "=" * 60)
    print("  Finance AI Agent — Kelly Criterion Test")
    print("=" * 60 + "\n")

    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        # Health check first
        health = client.get("/health")
        if health.status_code != 200:
            print("[ERR] API is not healthy. Make sure Docker containers are running.")
            sys.exit(1)
        print(f"[OK] API healthy: {health.json()['status']}\n")

        # Auth flow
        register_user(client)
        user_token = login_user(client)
        session_token = create_session(client, user_token)

        # Ask the agent
        print(f"\nQuestion:\n  {question}\n")
        print("Waiting for agent response...\n")
        answer = chat(client, session_token, question)

    print("-" * 60)
    print("Agent Response:")
    print("-" * 60)
    print(answer)
    print("-" * 60 + "\n")


if __name__ == "__main__":
    main()
