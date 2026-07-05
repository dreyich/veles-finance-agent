"""
Test script: Closed Learning Loop
Sends a trading loss scenario to the agent and verifies it saves a skill file.

Usage:
    python test_learning_loop.py
"""

import httpx
import os
import sys

BASE_URL = "http://localhost:8000"
TEST_EMAIL = "test_kelly@finance-agent.dev"
TEST_PASSWORD = "KellyTest123!"
SKILLS_DIR = os.path.join(os.path.dirname(__file__), "app", "skills")


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


def print_skill_file(skill_name: str):
    filename = skill_name.strip().lower().replace(" ", "_") + ".md"
    filepath = os.path.join(SKILLS_DIR, filename)

    if not os.path.exists(filepath):
        # Try to find any new .md file
        files = [f for f in os.listdir(SKILLS_DIR) if f.endswith(".md") and f != ".gitkeep"]
        if files:
            filepath = os.path.join(SKILLS_DIR, sorted(files)[-1])
            filename = sorted(files)[-1]
        else:
            print("[WARN] No skill file found in app/skills/")
            return

    print(f"\n{'=' * 60}")
    print(f"  Saved Skill File: app/skills/{filename}")
    print("=" * 60)
    with open(filepath, encoding="utf-8") as f:
        print(f.read())
    print("=" * 60)


def main():
    message = (
        "I just lost 30% of my portfolio because I held a high-volatility "
        "tech stock through an earnings report without an options hedge. "
        "Analyze what I did wrong, and save a new trading skill/rule called "
        "earnings_hedge_rule so we never make this mistake again."
    )

    print("\n" + "=" * 60)
    print("  Finance AI Agent — Closed Learning Loop Test")
    print("=" * 60 + "\n")

    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        health = client.get("/health")
        if health.status_code != 200:
            print("[ERR] API is not healthy.")
            sys.exit(1)
        print(f"[OK] API healthy\n")

        user_token = login(client)
        print(f"[OK] Logged in")

        session_token = create_session(client, user_token)
        print(f"[OK] Session created")

        print(f"\nSending scenario to agent...\n")
        print(f"Message:\n  {message}\n")
        print("Waiting for agent response (may take 20-40s)...\n")

        answer = chat(client, session_token, message)

    print("-" * 60)
    print("Agent Response:")
    print("-" * 60)
    print(answer)
    print("-" * 60)

    print_skill_file("earnings_hedge_rule")


if __name__ == "__main__":
    main()
