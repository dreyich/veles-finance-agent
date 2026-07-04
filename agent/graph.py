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

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from .tools import TOOLS

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
- For stock analysis: use get_market_data first, then due_diligence_report if needed
- For deep fundamental analysis: use fetch_sec_10k_tool
- A tool's raw output is a REPORT, not a hint. Your final answer must carry
  forward every line item it returned — every metric, every year-over-year
  change, every verdict and risk it lists — not a cherry-picked subset.
  If a tool returns 10 line items, your answer should reference all 10, not
  the 2 that seemed most important to you. Never compress a structured
  report down to one vague sentence like "strong growth" or "high potential".
- Concise means no filler wording, not fewer facts.
- Be professional in your final answers""")


class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]


def agent_node(state: AgentState) -> dict:
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


tool_node = ToolNode(TOOLS)

_builder = StateGraph(AgentState)
_builder.add_node("agent", agent_node)
_builder.add_node("tools", tool_node)
_builder.set_entry_point("agent")
_builder.add_conditional_edges("agent", should_continue)
_builder.add_edge("tools", "agent")

graph = _builder.compile()
