"""
Test script: Secure Code Execution Sandbox
Asks the agent to write and execute Python code for moving average calculation.

Usage:
    python test_sandbox.py
"""

import httpx
import sys

BASE_URL = "http://localhost:8000"
TEST_EMAIL = "test_kelly@finance-agent.dev"
TEST_PASSWORD = "KellyTest123!"


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


def chat(client: httpx.Client, session_token: str, message: str) -> str:
    resp = client.post(
        f"{BASE_URL}/api/v1/chatbot/chat",
        headers={"Authorization": f"Bearer {session_token}"},
        json={"messages": [{"role": "user", "content": message}]},
        timeout=90.0,
    )
    resp.raise_for_status()
    for msg in reversed(resp.json()["messages"]):
        if msg["role"] == "assistant":
            return msg["content"]
    return "(no response)"


def main():
    message = (
        "I need you to write a Python script that calculates the 10-day moving average "
        "of this dummy price array: [100, 102, 101, 105, 110, 108, 107, 112, 115, 113, "
        "118, 120, 119, 122, 125]. "
        "Execute the script using your sandbox tool and give me the final result."
    )

    print("\n" + "=" * 60)
    print("  Finance AI Agent — Sandbox Code Execution Test")
    print("=" * 60 + "\n")

    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        health = client.get("/health")
        if health.status_code != 200:
            print("[ERR] API is not healthy.")
            sys.exit(1)
        print("[OK] API healthy\n")

        user_token = login(client)
        print("[OK] Logged in")

        session_token = create_session(client, user_token)
        print("[OK] Session created")

        print(f"\nMessage:\n  {message}\n")
        print("Waiting for agent response (sandbox execution may take 10-20s)...\n")

        answer = chat(client, session_token, message)

    print("-" * 60)
    print("Agent Response:")
    print("-" * 60)
    print(answer)
    print("-" * 60 + "\n")


if __name__ == "__main__":
    main()
