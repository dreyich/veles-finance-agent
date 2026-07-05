"""
LangGraph agent — Orchestrator-Worker architecture.

  Orchestrator: llama3.1:8b  — handles tool calling (routing, planning)
  Worker:       veles:latest  — called internally by each tool for financial extraction

The orchestrator decides WHICH tool to call and with WHAT arguments.
Veles runs inside each tool function for domain-specific extraction.

Environment variables:
  ORCHESTRATOR_BASE_URL  — base URL for orchestrator model (default: Ollama localhost)
  ORCHESTRATOR_MODEL     — model name for orchestrator (default: llama3.1:8b)
"""
from __future__ import annotations
import os
from typing import Annotated, List
from typing_extensions import TypedDict

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from .tools import TOOLS

# Hard cap on tool-call rounds per request. Without this, a slow/failing tool
# (e.g. Yahoo Finance rate-limiting) combined with the orchestrator retrying
# the same call on its own can chain multiple ~30s tool rounds back to back,
# blowing past the frontend's request timeout with no user-facing message at
# all — a bounded "I couldn't get this" beats an unbounded network error.
MAX_TOOL_CALLS = 4

ORCHESTRATOR_BASE_URL = os.getenv("ORCHESTRATOR_BASE_URL", "http://localhost:11434/v1")
# Dev default: llama3.2:3b (fits with Veles 7B on single GPU)
# Prod default: llama3.1:8b via .env.production (RunPod A40 has 48GB)
ORCHESTRATOR_MODEL = os.getenv("ORCHESTRATOR_MODEL", "llama3.2:3b")

# ── Orchestrator: llama3.1:8b — strong, reliable tool calling ────────────────
orchestrator = ChatOpenAI(
    base_url=ORCHESTRATOR_BASE_URL,
    api_key=os.getenv("ORCHESTRATOR_API_KEY", "ollama"),
    model=ORCHESTRATOR_MODEL,
    temperature=0,
)

orchestrator_with_tools = orchestrator.bind_tools(TOOLS)

SYSTEM_PROMPT = SystemMessage(content="""You are Veles, an institutional financial analyst AI.

You have access to these tools:
- get_market_data: Live price, fundamentals, news for any stock
- due_diligence_report: Full DD report with APPROVED/REJECTED verdict
- kelly_position_size: Optimal position sizing via Kelly Criterion
- fetch_sec_10k_tool: Latest 10-K annual report from SEC EDGAR
- compare_annual_reports: Year-over-year 10-K comparison — what changed vs last year
- get_earnings_calendar: Next earnings date + analyst EPS/revenue estimates
- screen_stocks: Screen stocks in a sector by P/E, beta, and profit margin
- get_fx_rate: Official NBU exchange rate for a currency vs UAH (e.g. USD, EUR, PLN)

Rules:
- Always use tools to get real data before answering financial questions
- Call ONLY the tool(s) that directly answer what the user asked — not
  every tool that could theoretically be related. A request to pull figures
  from one company's 10-K needs only fetch_sec_10k_tool; it does not also
  need screen_stocks, get_market_data, or due_diligence_report. Each extra
  tool call adds real latency (live network calls per ticker), so unrelated
  tools aren't just noise, they make the user wait longer for no reason.
- Resolve company names to their correct ticker before calling a tool,
  regardless of language or grammatical case (e.g. Ukrainian "Тесла"/"тесли"/
  "теслу" -> TSLA, "Епл"/"Епла" -> AAPL, "Майкрософт"/"Майкрософта" -> MSFT).
  Never substitute a different, more familiar company's ticker when you're
  unsure — if the company truly can't be identified, ask the user to
  confirm the ticker instead of guessing one.
- For "what changed" or trend questions: use compare_annual_reports
- For earnings timing questions: use get_earnings_calendar
- For "find me stocks" or screening: use screen_stocks
- For currency/exchange rate questions (курс долара, євро, злотого etc.): use
  get_fx_rate with the 3-letter ISO code (USD, EUR, PLN...). Never call
  get_market_data with a currency code or FX pair as the ticker (e.g. "USD",
  "USDUAH") — get_market_data is for company stocks only (AAPL, MSFT, TSLA).
- For stock analysis: use get_market_data first, then due_diligence_report if needed
- For deep fundamental analysis: use fetch_sec_10k_tool
- A tool's raw output is a REPORT, not a hint. Your final answer must carry
  forward every line item it returned — every metric, every year-over-year
  change, every verdict and risk it lists — not a cherry-picked subset.
  If a tool returns 10 line items, your answer should reference all 10, not
  the 2 that seemed most important to you. Never compress a structured
  report down to one vague sentence like "strong growth" or "high potential".
  This rule applies to analytical reports (due diligence, 10-K comparisons,
  screening results) — it does NOT mean padding a simple lookup with filler.
- Concise means no filler wording, not fewer facts.
- If a tool returned a specific number (a rate, a price, a ratio), your
  answer MUST state that exact number. Never reply with something generic
  like "let me know if you need more info" instead of the actual figure —
  that is a wrong answer, not a short one.
- Match response length to what was actually asked:
  - Simple factual lookups (a single price, a single rate, one specific
    number, yes/no) get a direct 1-2 sentence answer. No preamble, no
    restating the question, no unrequested extra analysis.
  - Analytical questions (due diligence, comparisons, "why", "should I",
    trend/outlook questions, anything a tool returned a multi-line report
    for) get the full answer with every relevant data point, per the rule
    above.
  - If unsure which this is, judge by what the user actually asked for —
    not by how much data happens to be available.
- Be professional in your final answers""")


class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    tool_call_count: int


def agent_node(state: AgentState) -> dict:
    if state.get("tool_call_count", 0) >= MAX_TOOL_CALLS:
        limit_msg = AIMessage(content=(
            "Досягнуто ліміт звернень до інструментів для цього запиту "
            "(дані, схоже, тимчасово недоступні). Спробуйте, будь ласка, "
            "повторити трохи пізніше або перефразувати питання."
        ))
        return {"messages": [limit_msg]}

    messages = state["messages"]
    # Inject system prompt if first turn
    if not any(isinstance(m, SystemMessage) for m in messages):
        messages = [SYSTEM_PROMPT] + list(messages)
    response = orchestrator_with_tools.invoke(messages)
    return {"messages": [response]}


def should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    return END


# Every tool in TOOLS reports failure by returning a plain string starting
# with one of these markers (never raises — @tool wrappers catch their own
# exceptions), rather than a structured error type. Without this check, a
# failed live call (rate limit, missing ticker, bad sector) flows into the
# orchestrator's context looking identical to a successful report, and
# nothing stops the LLM from citing it as real data.
_TOOL_FAILURE_PREFIXES = (
    "Error fetching",
    "SEC EDGAR Error",
    "10-K fetched",  # "...but extraction failed: ..."
    "Cannot find SEC data",
    "No XBRL data available",
    "Unknown sector",
)

_raw_tool_node = ToolNode(TOOLS)


def tool_node(state: AgentState) -> dict:
    result = _raw_tool_node.invoke(state)
    for msg in result.get("messages", []):
        content = getattr(msg, "content", None)
        if isinstance(content, str) and content.startswith(_TOOL_FAILURE_PREFIXES):
            msg.content = (
                "[TOOL CALL FAILED — this is not real data, do not present it "
                f"as such; tell the user the lookup failed] {content}"
            )
    last_ai = state["messages"][-1]
    calls_made = len(getattr(last_ai, "tool_calls", None) or [])
    result["tool_call_count"] = state.get("tool_call_count", 0) + calls_made
    return result

_builder = StateGraph(AgentState)
_builder.add_node("agent", agent_node)
_builder.add_node("tools", tool_node)
_builder.set_entry_point("agent")
_builder.add_conditional_edges("agent", should_continue)
_builder.add_edge("tools", "agent")

graph = _builder.compile()
