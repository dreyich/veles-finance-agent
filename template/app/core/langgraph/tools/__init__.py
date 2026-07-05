"""LangGraph tools for enhanced language model capabilities.

This package contains custom tools that can be used with LangGraph to extend
the capabilities of language models. Currently includes tools for web search
and other external integrations.
"""

from langchain_core.tools.base import BaseTool

from .ask_human import ask_human
from .dd_report_tools import generate_dd_report
from .duckduckgo_search import duckduckgo_search_tool
from .macro_math_tools import (
    calculate_dcf,
    calculate_debt_sustainability,
    calculate_irp,
    calculate_real_yields,
)
from .macro_tools import get_fx_rates, get_global_macro_data, get_us_macro_data, get_yield_curve
from .market_data_tools import get_market_data
from .memory_tools import list_trading_skills, save_trading_skill
from .quantoracle_tools import kelly_criterion_calculator
from .sandbox_tools import execute_python_sandbox
from .schema_tools import read_tool_schema, register_tool_schema
from .skill_tools import load_skill

tools: list[BaseTool] = [
    read_tool_schema,
    duckduckgo_search_tool,
    ask_human,
    # Phase 3.2 — progressive disclosure
    load_skill,
    # Market data
    get_market_data,
    generate_dd_report,
    # Macro — live data
    get_us_macro_data,
    get_global_macro_data,
    get_fx_rates,
    get_yield_curve,
    # Macro — deterministic math (NO LLM estimation)
    calculate_irp,
    calculate_real_yields,
    calculate_dcf,
    calculate_debt_sustainability,
    # Position sizing & risk
    kelly_criterion_calculator,
    # Code execution
    execute_python_sandbox,
    # Memory
    save_trading_skill,
    list_trading_skills,
]

# Lite tool set for models with limited context windows (Llama 3.3 70B: max_model_len=8192).
# Excludes ask_human (causes echo-response issues) and heavy tools that rarely fit.
# Phase 2.1: execute_python_sandbox added for deterministic custom calculations.
# Phase 3.2: load_skill added for progressive disclosure (replaces bloated blueprints).
tools_lite: list[BaseTool] = [
    load_skill,
    get_fx_rates,
    get_us_macro_data,
    get_global_macro_data,  # GDP, inflation, unemployment for any country incl. Ukraine
    get_market_data,
    calculate_irp,
    kelly_criterion_calculator,
    duckduckgo_search_tool,
    execute_python_sandbox,
]

# ── Register schemas for Progressive Disclosure ───────────────────────────────
# Each tool's full JSON schema is stored once at startup.
# The agent fetches it on demand via read_tool_schema(tool_name).
for _tool in tools:
    if _tool.name == "read_tool_schema":
        continue
    _args_schema = getattr(_tool, "args_schema", None)
    if _args_schema and hasattr(_args_schema, "model_json_schema"):
        register_tool_schema(
            name=_tool.name,
            description=str(_tool.description or ""),
            parameters=_args_schema.model_json_schema(),
        )
