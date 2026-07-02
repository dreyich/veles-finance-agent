"""
One-off script to send a real x402 payment against the live gateway
and confirm settlement. Run this yourself — never share your private
key with anyone, including Claude.

Usage:
    export EVM_PRIVATE_KEY=0x...        # wallet that holds USDC on Base mainnet
    python test_x402_payment.py

Uses the cheapest endpoint (/kelly, $0.01) to minimize cost of the test.
"""
import asyncio
import os

from eth_account import Account
from x402 import x402Client
from x402.http.clients import x402HttpxClient
from x402.mechanisms.evm import EthAccountSigner
from x402.mechanisms.evm.exact.register import register_exact_evm_client

GATEWAY_URL = os.getenv("GATEWAY_URL", "https://veles-finance-gateway.fly.dev")
PRIVATE_KEY = os.environ["EVM_PRIVATE_KEY"]  # fails loudly if not set


async def main() -> None:
    account = Account.from_key(PRIVATE_KEY)
    print(f"Paying from wallet: {account.address}")

    client = x402Client()
    register_exact_evm_client(client, EthAccountSigner(account))

    async with x402HttpxClient(client, base_url=GATEWAY_URL) as http:
        resp = await http.post(
            "/kelly",
            params={"win_probability": 0.55, "payout_ratio": 1.5},
        )
        print(f"Status: {resp.status_code}")
        print(f"Body: {resp.text}")
        settlement_header = resp.headers.get("x-payment-response")
        if settlement_header:
            print(f"Settlement info: {settlement_header}")


if __name__ == "__main__":
    asyncio.run(main())
