"""
Veles Finance MCP Server
Exposes financial analysis tools via Model Context Protocol.
Each tool call makes a paid request to veles-finance-gateway.fly.dev (x402/USDC).

Usage (Claude Desktop / Cursor):
  {
    "mcpServers": {
      "veles-finance": {
        "command": "python",
        "args": ["path/to/mcp_server.py"],
        "env": {
          "VELES_WALLET_KEY": "<your-base-wallet-private-key>"
        }
      }
    }
  }

Dependencies: pip install mcp httpx x402
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

GATEWAY = os.getenv("VELES_GATEWAY_URL", "https://veles-finance-gateway.fly.dev")
WALLET_KEY = os.getenv("VELES_WALLET_KEY", "")

# Try to load x402 httpx extension (auto-pays 402 responses with USDC on Base)
try:
    from x402.client.httpx import x402_client
    _HAS_X402 = True
except ImportError:
    _HAS_X402 = False


def _make_client() -> httpx.AsyncClient:
    if _HAS_X402 and WALLET_KEY:
        return x402_client(private_key=WALLET_KEY, timeout=60.0)
    return httpx.AsyncClient(timeout=60.0)


async def _post_json(path: str, body: dict) -> dict:
    async with _make_client() as client:
        r = await client.post(f"{GATEWAY}{path}", json=body)
        if r.status_code == 402 and not (_HAS_X402 and WALLET_KEY):
            return {
                "error": "Payment required (HTTP 402)",
                "instructions": r.json(),
                "hint": "Set VELES_WALLET_KEY env var with a Base-network private key holding USDC.",
            }
        r.raise_for_status()
        return r.json()


async def _post_params(path: str, params: dict) -> dict:
    async with _make_client() as client:
        r = await client.post(f"{GATEWAY}{path}", params=params)
        if r.status_code == 402 and not (_HAS_X402 and WALLET_KEY):
            return {
                "error": "Payment required (HTTP 402)",
                "instructions": r.json(),
                "hint": "Set VELES_WALLET_KEY env var with a Base-network private key holding USDC.",
            }
        r.raise_for_status()
        return r.json()


TOOLS: list[Tool] = [
    Tool(
        name="veles_agent",
        description=(
            "Full LangGraph financial agent. Routes your question to the right tool: "
            "market data, SEC 10-K extraction, due diligence, Kelly Criterion, or YoY comparison. "
            "Use for open-ended financial questions. Cost: $0.05 USDC per call."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Financial question or analysis request. E.g. 'Compare Apple revenue YoY vs Microsoft'",
                },
                "history": {
                    "type": "array",
                    "description": "Optional conversation history for multi-turn context.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "role": {"type": "string", "enum": ["user", "assistant"]},
                            "content": {"type": "string"},
                        },
                        "required": ["role", "content"],
                    },
                    "default": [],
                },
            },
            "required": ["message"],
        },
    ),
    Tool(
        name="veles_due_diligence",
        description=(
            "Deterministic stock screening. Returns APPROVED or REJECTED with P/E, beta, "
            "profit margin analysis tailored to your risk profile. "
            "Cost: $0.02 USDC per call."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol, e.g. AAPL, NVDA, MSFT",
                },
                "risk_profile": {
                    "type": "string",
                    "enum": ["conservative", "moderate", "aggressive"],
                    "description": "Your investment risk tolerance.",
                    "default": "moderate",
                },
            },
            "required": ["ticker"],
        },
    ),
    Tool(
        name="veles_sec_10k",
        description=(
            "Extract key financials from the latest SEC 10-K annual report via EDGAR. "
            "Returns revenue, net income, EPS, debt-to-equity and other core metrics. "
            "Cost: $0.02 USDC per call."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol, e.g. AAPL, TSLA",
                },
            },
            "required": ["ticker"],
        },
    ),
    Tool(
        name="veles_ask",
        description=(
            "Ask Veles-Finance-7B a direct financial question. Lighter than the full agent — "
            "best for factual questions about markets, ratios, or terminology. "
            "Cost: $0.02 USDC per call."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Financial question, e.g. 'What is the Sharpe ratio?'",
                },
            },
            "required": ["message"],
        },
    ),
    Tool(
        name="veles_kelly",
        description=(
            "Calculate Kelly Criterion position sizing for a trade. "
            "Returns optimal bet fraction given your win rate and payoff ratio. "
            "Cost: $0.01 USDC per call."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "win_rate": {
                    "type": "number",
                    "description": "Historical win rate as decimal, e.g. 0.55 for 55%",
                },
                "win_loss_ratio": {
                    "type": "number",
                    "description": "Average win size divided by average loss size, e.g. 1.5",
                },
            },
            "required": ["win_rate", "win_loss_ratio"],
        },
    ),
]


app = Server("veles-finance")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        if name == "veles_agent":
            result = await _post_json("/agent", {
                "message": arguments["message"],
                "history": arguments.get("history", []),
            })
        elif name == "veles_due_diligence":
            result = await _post_params("/due-diligence", {
                "ticker": arguments["ticker"],
                "risk_profile": arguments.get("risk_profile", "moderate"),
            })
        elif name == "veles_sec_10k":
            result = await _post_params("/sec", {"ticker": arguments["ticker"]})
        elif name == "veles_ask":
            result = await _post_json("/ask", {"message": arguments["message"]})
        elif name == "veles_kelly":
            result = await _post_params("/kelly", {
                "win_rate": arguments["win_rate"],
                "win_loss_ratio": arguments["win_loss_ratio"],
            })
        else:
            result = {"error": f"Unknown tool: {name}"}
    except httpx.HTTPStatusError as e:
        result = {"error": f"HTTP {e.response.status_code}", "detail": e.response.text}
    except Exception as e:
        result = {"error": str(e)}

    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
