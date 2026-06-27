# veles-finance-mcp

Institutional Due Diligence tools for Claude Desktop, Cursor, Windsurf — one command to install.

## Install

```bash
uvx veles-finance-mcp
```

## Claude Desktop config

Add to `~/.claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "veles-finance": {
      "command": "uvx",
      "args": ["veles-finance-mcp"]
    }
  }
}
```

## Tools

| Tool | What it does |
|---|---|
| `get_market_data` | Live price, P/E, beta, news for any ticker via yfinance |
| `due_diligence_report` | Full DD report with APPROVED/REJECTED verdict |
| `kelly_position_size` | Optimal position sizing via Kelly Criterion |

## Example

After connecting, ask Claude:

> "Analyse NVDA for a conservative investor"

Claude will call `due_diligence_report("NVDA", "conservative")` and return a structured report ending with `VERDICT: APPROVED ✓` or `VERDICT: REJECTED ✗`.
