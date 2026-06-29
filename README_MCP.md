# Veles Finance MCP Server

AI-powered financial analysis via [Model Context Protocol](https://modelcontextprotocol.io). Each tool call is automatically paid with **$0.01–$0.05 USDC** on Base network via [x402](https://x402.org) protocol.

## Install

```bash
pip install veles-finance-mcp
# With auto-payment support:
pip install "veles-finance-mcp[autopay]"
```

## Configure (Claude Desktop / Cursor)

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "veles-finance": {
      "command": "veles-finance-mcp",
      "env": {
        "VELES_WALLET_KEY": "<your-base-wallet-private-key-with-usdc>"
      }
    }
  }
}
```

## Tools

| Tool | Description | Cost |
|------|-------------|------|
| `veles_agent` | Full LangGraph agent — routes to all tools, multi-turn | $0.05 USDC |
| `veles_due_diligence` | Stock screening: APPROVED/REJECTED with P/E, beta, margins | $0.02 USDC |
| `veles_sec_10k` | Extract key financials from latest SEC 10-K via EDGAR | $0.02 USDC |
| `veles_ask` | Direct question to Veles-Finance-7B model | $0.02 USDC |
| `veles_kelly` | Kelly Criterion position sizing calculator | $0.01 USDC |

## Example usage in Claude

```
"Do due diligence on NVDA stock with aggressive risk profile"
→ veles_due_diligence(ticker="NVDA", risk_profile="aggressive")
→ Pays $0.02 USDC automatically → Returns APPROVED/REJECTED + analysis
```

## Payment

- Network: **Base** (Ethereum L2)
- Asset: **USDC** (`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`)
- Facilitator: **x402.org**
- No wallet key = returns payment instructions for manual payment

## Links

- Gateway: https://veles-finance-gateway.fly.dev
- x402 manifest: https://veles-finance-gateway.fly.dev/.well-known/x402
- AI discovery: https://veles-finance-gateway.fly.dev/llms.txt
- Model: [Drushka/Veles-Finance-7B-v5](https://huggingface.co/Drushka/Veles-Finance-7B-v5) (94.3% accuracy on 10-K extraction)
