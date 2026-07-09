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
# Dev default: llama3.2:3b (lightweight, fits with Veles 7B on single GPU)
# Prod default: llama-3.1-70b-versatile via Groq (.env.production)
# Groq is free (with rate limits) and much smarter than 8b models for complex reasoning
ORCHESTRATOR_MODEL = os.getenv("ORCHESTRATOR_MODEL", "llama3.2:3b")

# Override stale RunPod template zy5axupfpa which has llama-3.1-8b-instant
if ORCHESTRATOR_MODEL == "llama-3.1-8b-instant":
    ORCHESTRATOR_MODEL = "llama-3.1-70b-versatile"
    print(f"[orchestrator] Overriding stale template model to {ORCHESTRATOR_MODEL}")

# Printed at import time (not just logged on failure) because the previous
# silent fallback to the Ollama default cost real debugging time: a
# production entrypoint that forgets to set ORCHESTRATOR_BASE_URL doesn't
# error at startup, it just points at a URL that doesn't exist in that
# container and only fails later, on the first real chat request.
print(f"[orchestrator] base_url={ORCHESTRATOR_BASE_URL} model={ORCHESTRATOR_MODEL}")

# ── Orchestrator: llama-3.1-70b (Groq) — strong reasoning & tool calling ──────
orchestrator = ChatOpenAI(
    base_url=ORCHESTRATOR_BASE_URL,
    api_key=os.getenv("ORCHESTRATOR_API_KEY", "ollama"),
    model=ORCHESTRATOR_MODEL,
    temperature=0,
)

SYSTEM_PROMPT = SystemMessage(content="""You are Veles, an institutional financial analyst AI.

You have access to these tools:
- get_market_data: Live price, fundamentals, news for any stock
- due_diligence_report: Full DD report with APPROVED/REJECTED verdict
- kelly_position_size: Optimal position sizing via Kelly Criterion
- fetch_sec_10k_tool: Latest 10-K annual report from SEC EDGAR
- compare_annual_reports: Year-over-year 10-K comparison — what changed vs last year
- get_earnings_calendar: Next earnings date + analyst EPS/revenue estimates
- screen_stocks: Screen stocks in a sector by P/E, beta, and profit margin
- get_fx_rate: Exchange rates - single code for NBU rate vs UAH (USD, EUR), or pair for cross-rates (USD/EUR, EUR/GBP)
- web_search: Search the web for current information not available in other tools (crypto, commodities, news, economic indicators)

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
- get_market_data and due_diligence_report accept multiple tickers in ONE
  call as a comma-separated string (e.g. "AAPL,MSFT,GOOGL"). When comparing
  or analyzing several companies, pass every ticker in a single call to the
  same tool — never call the same tool once per ticker. This isn't just an
  efficiency preference: each separate tool call is an extra round-trip that
  can fail, so batching tickers into one call is more reliable, not just faster.
- For "what changed" or trend questions: use compare_annual_reports
- For earnings timing questions: use get_earnings_calendar
- For "find me stocks" or screening: use screen_stocks
- For currency/exchange rate questions (курс долара, євро, злотого etc.): use
  get_fx_rate. For rates vs UAH, pass a single code (e.g. "USD", "EUR"). For
  cross-currency rates (USD to EUR, GBP to USD), pass a pair separated by
  slash (e.g. "USD/EUR", "GBP/USD"). Never call get_market_data with a
  currency code or FX pair as the ticker (e.g. "USD", "USDUAH") —
  get_market_data is for company stocks only (AAPL, MSFT, TSLA).
- For cryptocurrency questions (Bitcoin, Ethereum, crypto prices): use web_search
- For commodity prices (gold, oil, silver, wheat, etc.): use web_search
- For economic indicators (inflation, GDP, unemployment): use web_search
- For recent financial news not in get_market_data: use web_search
- For private companies or startups (not publicly traded): use web_search
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
- NEVER state a number (market cap, P/E, revenue, any fundamental) from your
  own training knowledge if it wasn't in a tool's output this turn — even if
  you already have a price for that ticker earlier in the conversation. Stock
  data changes constantly and your training data is stale; a remembered
  figure presented as current is a hallucination, not an estimate. If a tool
  result says a field is unavailable (e.g. "fundamentals unavailable"), say
  so plainly ("I don't have current market cap data for X") instead of
  filling the gap from memory. Call the tool again if you need the number
  and don't already have it from this turn's tool results.
- If a tool returned a specific number (a rate, a price, a ratio), your
  answer MUST state that exact number. Never reply with something generic
  like "let me know if you need more info" instead of the actual figure —
  that is a wrong answer, not a short one.
  Example — get_fx_rate("USD") returns "NBU official rate — Долар США (USD):
  44.5696 UAH as of 06.07.2026". Your answer must be like:
  "Курс долара до гривні станом на 06.07.2026: 44.57 UAH за 1 USD (НБУ)."
  Example — get_fx_rate("USD/EUR") returns "Exchange rate — USD/EUR: 0.9245".
  Your answer must be: "Курс долара до євро: 1 USD = 0.9245 EUR."
  Example — get_market_data returns "Market Data — AAPL ... Price: $308.63
  Change: +14.25 (+4.84%) ...". Your answer must state that price, e.g.
  "Акції Apple (AAPL) зараз коштують $308.63 (+4.84% за день)."
  NOT "Ask me again if you want the latest data" or "If you need more
  info, let me know" — those responses have zero information value and
  are always wrong when a number was available in the tool result.
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


def should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    return END


# Every tool reports failure by returning a plain string starting with one of
# these markers (never raises — @tool wrappers catch their own exceptions),
# rather than a structured error type. Without this check, a failed live call
# (rate limit, missing ticker, bad sector) flows into the orchestrator's
# context looking identical to a successful report, and nothing stops the LLM
# from citing it as real data.
_TOOL_FAILURE_PREFIXES = (
    "Error fetching",
    "SEC EDGAR Error",
    "10-K fetched",  # "...but extraction failed: ..."
    "Cannot find SEC data",
    "No XBRL data available",
    "Unknown sector",
)


def build_agent_graph(tools: list):
    """Compile an agent graph bound to a specific tool list.

    Callers on different infrastructure need different tools for the same
    orchestrator: main.py (running inside the Veles RunPod container) uses
    fetch_sec_10k_tool's in-process variant (agent/tools.py), while
    gateway.py (always-on, no Veles/GPU access) uses the remote variant
    (agent/tools_edge.py) that hits Veles over HTTP only when actually
    invoked. Everything else about the graph is identical either way.
    """
    orchestrator_with_tools = orchestrator.bind_tools(tools)
    raw_tool_node = ToolNode(tools)

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
        # Groq's tool-calling grammar for llama-3.1-8b-instant occasionally
        # rejects a well-formed call (400 tool_use_failed) even when the model
        # picked the right tool and arguments — a known reliability gap in their
        # constrained decoding, not a bug in our prompt or tools. Left uncaught,
        # this crashed the whole request (surfacing as a dropped connection /
        # NetworkError on the frontend) instead of a normal answer. It's
        # non-deterministic, so a few retries clear most transient rejections;
        # only degrade to a plain apology once all of them are exhausted.
        _MAX_ORCHESTRATOR_ATTEMPTS = 3
        response = None
        for attempt in range(_MAX_ORCHESTRATOR_ATTEMPTS):
            try:
                response = orchestrator_with_tools.invoke(messages)
                break
            except Exception:
                if attempt == _MAX_ORCHESTRATOR_ATTEMPTS - 1:
                    response = AIMessage(content=(
                        "Вибачте, не вдалось обробити цей запит через тимчасову "
                        "помилку виклику інструмента. Спробуйте, будь ласка, "
                        "перефразувати питання або повторити за хвилину."
                    ))
        return {"messages": [response]}

    def tool_node(state: AgentState) -> dict:
        result = raw_tool_node.invoke(state)
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

    builder = StateGraph(AgentState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_node)
    builder.set_entry_point("agent")
    builder.add_conditional_edges("agent", should_continue)
    builder.add_edge("tools", "agent")
    return builder.compile()


# Default graph — in-process Veles access, used by main.py (runs inside the
# same RunPod container as Veles SGLang).
graph = build_agent_graph(TOOLS)

# Kept at module level for tests_orchestrator.py, which checks the
# orchestrator's tool-routing decisions directly against the default tool set.
orchestrator_with_tools = orchestrator.bind_tools(TOOLS)
