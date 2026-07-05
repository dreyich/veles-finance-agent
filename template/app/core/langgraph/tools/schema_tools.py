"""Progressive Disclosure — Tool Schema Registry.

Instead of injecting all tool schemas into every LLM context window
(expensive: ~200-600 tokens per tool × N tools), this module exposes a
single lightweight `read_tool_schema` tool.

Flow:
  1. System prompt lists tools as one-liners (~5 tokens each).
  2. Agent decides it needs a tool → calls read_tool_schema(tool_name).
  3. Agent receives full JSON schema (~80-200 tokens) for that tool only.
  4. Agent executes the tool with correct parameters.

Token savings (6-tool setup):
  Before: ~1800 tokens of schemas per request  (injected by LangChain)
  After:  ~30 tokens (tool list) + ~120 tokens (one schema on demand)
  Saving: ~1650 tokens (~92%) on requests that use 0-1 tools.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  FUTURE: XGrammar / SGLang Constrained Decoding
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
When we later plug in a self-hosted inference engine (SGLang / vLLM),
we will replace the OpenRouter API call with a constrained-decoding call:

  from sglang import Runtime, gen
  from xgrammar import GrammarCompiler, BNFGrammar

  # Convert Pydantic schema → BNF grammar → compiled grammar
  schema_json = KellyInput.model_json_schema()
  grammar     = GrammarCompiler.compile_json_schema(json.dumps(schema_json))

  # Force the model to produce ONLY tokens that match the grammar
  with Runtime("qwen/qwen-2.5-72b-instruct") as rt:
      result = rt.run(
          prompt   = messages,
          sampling = gen(max_tokens=512, grammar=grammar),
      )

This makes syntactically invalid JSON architecturally impossible — the
sampler physically cannot produce a closing `}` before all required
fields are filled, eliminating all schema-validation errors at zero
extra latency cost.

Reference: https://xgrammar.mlc.ai / https://github.com/sgl-project/sglang
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
from typing import Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

# ── Tool Schema Registry ──────────────────────────────────────────────────────
# Populated at import time by register_tool_schema().
# Stores: name → {"description": str, "parameters": dict}
_TOOL_REGISTRY: dict[str, dict] = {}


def register_tool_schema(name: str, description: str, parameters: dict) -> None:
    """Register a tool's full schema for on-demand retrieval.

    Called once per tool at application startup — no per-request cost.
    """
    _TOOL_REGISTRY[name] = {
        "name": name,
        "description": description,
        "parameters": parameters,
        "token_estimate": len(json.dumps(parameters)) // 4,
    }


def get_tool_catalog() -> str:
    """Return a compact one-liner catalog of all registered tools.

    Used by the system prompt to list tools without injecting full schemas.
    Each line is <50 chars — total cost ~5-8 tokens per tool.
    """
    if not _TOOL_REGISTRY:
        return "(no tools registered)"

    lines = []
    for name, meta in _TOOL_REGISTRY.items():
        short_desc = meta["description"].split("\n")[0][:80]
        lines.append(f"• {name}: {short_desc}")
    return "\n".join(lines)


class ReadSchemaInput(BaseModel):
    """Input schema for read_tool_schema."""
    tool_name: str = Field(
        ...,
        description="Exact name of the tool whose schema you want to retrieve.",
    )


@tool("read_tool_schema", args_schema=ReadSchemaInput)
def read_tool_schema(tool_name: str) -> str:
    """Fetch the full JSON schema of a tool before using it.

    REQUIRED: Call this tool first whenever you plan to use a complex tool
    (kelly_criterion_calculator, execute_python_sandbox, save_trading_skill).
    This gives you the exact parameter names, types, and constraints so you
    call the tool correctly on the first attempt.

    Args:
        tool_name: Exact name of the tool (e.g. 'kelly_criterion_calculator').

    Returns:
        Full JSON schema with parameter descriptions and constraints,
        or an error message if the tool name is not recognised.
    """
    if tool_name not in _TOOL_REGISTRY:
        available = ", ".join(_TOOL_REGISTRY.keys())
        return (
            f"Tool '{tool_name}' not found in registry.\n"
            f"Available tools: {available}"
        )

    meta = _TOOL_REGISTRY[tool_name]
    schema_str = json.dumps(meta["parameters"], indent=2)

    return (
        f"Tool: {meta['name']}\n"
        f"Description: {meta['description'][:300]}\n"
        f"Schema (~{meta['token_estimate']} tokens):\n"
        f"```json\n{schema_str}\n```"
    )
