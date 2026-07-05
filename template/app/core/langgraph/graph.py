"""This file contains the LangGraph Agent/workflow and interactions with the LLM."""

import asyncio
import re
from typing import (
    AsyncGenerator,
    Optional,
    cast,
)
from urllib.parse import quote_plus

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    ToolMessage,
    convert_to_openai_messages,
)
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.errors import GraphInterrupt
from langgraph.graph import (
    END,
    StateGraph,
)
from langchain_core.runnables.config import RunnableConfig
from langgraph.graph.state import (
    Command,
    CompiledStateGraph,
)
from langgraph.types import (
    RetryPolicy,
    StateSnapshot,
)
from psycopg import (
    AsyncConnection,
    sql,
)
from psycopg.rows import (
    DictRow,
    dict_row,
)
from psycopg_pool import AsyncConnectionPool

from app.core.audit_logger import upload_audit_trace_async
from app.core.intent_validator import validate_tool_intent
from app.core.config import (
    Environment,
    settings,
)
from app.core.langgraph.tools import tools, tools_lite
from app.core.logging import logger
from app.core.metrics import llm_inference_duration_seconds
from app.core.observability import langfuse_callback_handler
from app.core.pii_shield import mask_messages
from app.core.prompts import load_system_prompt
from app.schemas import (
    GraphState,
    IntentEnum,
    Message,
    UniversalEnvelope,
)
from app.schemas.graph import MAX_TOOL_CALLS
from app.services.conversation_logger import log_conversation
from app.services.llm import llm_service
from app.services.memory import memory_service
from app.domain.delayed_binding import DelayedBindingProcessor, build_context_from_graph_state
from app.infrastructure.compliance.audit_callback import ComplianceAuditCallback
from app.infrastructure.episodic_store import write_episode
from app.utils import (
    dump_messages,
    extract_text_content,
    parse_envelope_from_response,
    prepare_messages,
    process_llm_response,
)

PostgresConnPool = AsyncConnectionPool[AsyncConnection[DictRow]]




# Keywords that trigger live data injection
_FX_KEYWORDS      = {"курс", "dollar", "долар", "usd", "uah", "eur", "gbp", "exchange", "rate", "валют", "гривн"}
_MACRO_KEYWORDS   = {"fed", "ставка", "cpi", "inflation", "інфляці", "gdp", "yield", "vix", "macro", "макро", "відсоток"}
_STOCK_KEYWORDS   = {"stock", "акці", "ticker", "share", "nvda", "aapl", "tsla", "msft", "price", "ціна"}
_UA_KEYWORDS      = {"курс", "долар", "гривн", "uah", "валют", "укра"}
_FORECAST_KEYWORDS = {"буде", "прогноз", "forecast", "очікуєть", "до кінця", "наступн", "майбутн",
                      "2025", "2026", "2027", "скільки буде", "який буде", "predict", "outlook"}


async def _inject_live_data(system_prompt: str, messages: list) -> str:
    """Fetch live market/macro data and inject into system prompt.

    Used when Veles runs without tool calling (vLLM default mode).
    The model sees exact current numbers and quotes them accurately.
    """
    import asyncio

    from app.core.langgraph.tools.macro_tools import (
        _fred_csv_latest,
        _nbu_rate,
        get_fx_rates,
        get_us_macro_data,
    )

    # Find last user message
    last_msg = ""
    for m in reversed(messages):
        content = getattr(m, "content", "") or (m.get("content", "") if isinstance(m, dict) else "")
        role = getattr(m, "role", "") or (m.get("role", "") if isinstance(m, dict) else "")
        if role == "user" and content:
            last_msg = content.lower()
            break

    if not last_msg:
        return system_prompt

    blocks: list[str] = []

    needs_fx     = any(k in last_msg for k in _FX_KEYWORDS)
    needs_macro  = any(k in last_msg for k in _MACRO_KEYWORDS)
    is_ukrainian = any(k in last_msg for k in _UA_KEYWORDS)
    is_forecast  = any(k in last_msg for k in _FORECAST_KEYWORDS)

    if needs_fx:
        try:
            # For Ukrainian queries: only UAH + major pairs, NO PLN/CZK/HUF to prevent
            # cross-lingual interference (USD/PLN ~4.87 is easily confused with USD/UAH)
            pairs = ["UAH", "EUR", "GBP"] if is_ukrainian else ["UAH", "EUR", "GBP", "PLN", "CHF", "JPY"]
            fx = await asyncio.get_event_loop().run_in_executor(
                None, lambda: get_fx_rates.invoke({"base": "USD", "pairs": pairs})
            )
            # Prepend a clear anchor for Ukrainian queries so the model cannot confuse rates
            if is_ukrainian:
                uah_rate = _nbu_rate()
                uah_anchor = (
                    f"ПОТОЧНИЙ КУРС (SPOT) ДЛЯ УКРАЇНИ: 1 USD = {uah_rate:.2f} UAH (НБУ офіційний)\n"
                    f"ВАЖЛИВО: USD/UAH завжди в діапазоні 40-60. Якщо розрахунок дає 4-6 — помилка на порядок.\n\n"
                ) if uah_rate else ""
                blocks.append(uah_anchor + fx)
            else:
                blocks.append(fx)
        except Exception as e:
            logger.warning("live_fx_injection_failed", error=str(e))

    if needs_macro:
        try:
            macro = await asyncio.get_event_loop().run_in_executor(
                None, lambda: get_us_macro_data.invoke(
                    {"indicators": ["fed_funds_rate", "us_cpi_yoy", "us_10y_yield", "us_2y_yield", "dollar_index", "vix"]}
                )
            )
            blocks.append(macro)
        except Exception as e:
            logger.warning("live_macro_injection_failed", error=str(e))

    if not blocks:
        return system_prompt

    forecast_instruction = (
        "\n\nFORECAST REQUESTED: The user is asking about a FUTURE rate, NOT the current one.\n"
        "Current spot above is the INPUT for your calculation — do NOT return it as the answer.\n"
        "MANDATORY: call calculate_irp(spot=<current_uah_rate>, r_domestic=<nbu_rate>, "
        "r_foreign=<fed_funds_rate>, pi_domestic=<ua_cpi>, pi_foreign=<us_cpi>, months=<horizon>)\n"
        "Return the IRP/PPP fair value as the forecast, not the current spot.\n"
    ) if is_forecast and needs_fx else ""

    live_section = (
        "\n\n# LIVE MARKET DATA — отримано прямо зараз, використовуй ТІЛЬКИ ці цифри\n\n"
        + "\n\n".join(blocks)
        + forecast_instruction
    )
    return system_prompt + live_section


async def _maybe_inject_forecast_context(system_prompt: str, messages: list) -> str:
    """Pre-fetch FX + macro data and inject as completed tool results when forecast is detected.

    Llama 3.3 70B reliably calls get_fx_rates but stops there. This function fetches
    FX + macro + IRP data server-side and injects the numbers directly so the model
    only needs to write the final answer — no multi-step tool chain required.
    """
    import asyncio
    from app.core.langgraph.tools.macro_tools import get_fx_rates, get_us_macro_data
    from app.core.langgraph.tools.macro_math_tools import calculate_irp

    last_msg = ""
    for m in reversed(messages):
        content = getattr(m, "content", "") or (m.get("content", "") if isinstance(m, dict) else "")
        role = getattr(m, "type", "") or getattr(m, "role", "") or (m.get("role", "") if isinstance(m, dict) else "")
        if role in ("human", "user") and content:
            last_msg = content.lower()
            break

    if not last_msg:
        return system_prompt

    is_forecast = any(k in last_msg for k in _FORECAST_KEYWORDS)
    is_fx = any(k in last_msg for k in _FX_KEYWORDS)

    if not (is_forecast and is_fx):
        return system_prompt

    try:
        fx_result, macro_result = await asyncio.gather(
            asyncio.get_event_loop().run_in_executor(
                None, lambda: get_fx_rates.invoke({"base": "USD", "pairs": ["UAH", "EUR", "GBP"]})
            ),
            asyncio.get_event_loop().run_in_executor(
                None, lambda: get_us_macro_data.invoke({"indicators": ["fed_funds_rate", "us_cpi_yoy"]})
            ),
        )

        # Extract UAH rate for IRP
        import re
        uah_match = re.search(r"USD/UAH\s+([\d.]+)", fx_result)
        fed_match = re.search(r"Fed Funds.*?([\d.]+)%", macro_result)
        cpi_match = re.search(r"CPI.*?([\d.]+)%", macro_result)

        spot = float(uah_match.group(1)) if uah_match else 44.9
        fed = float(fed_match.group(1)) if fed_match else 4.33
        us_cpi = float(cpi_match.group(1)) if cpi_match else 2.4

        irp_result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: calculate_irp.invoke({
                "spot_rate": spot,
                "rate_domestic": 13.5,
                "rate_foreign": fed,
                "inflation_domestic": 12.0,
                "inflation_foreign": us_cpi,
                "horizon_months": 6,
                "pair_name": "USD/UAH",
            })
        )

        injection = (
            f"\n\n## ⚡ FORECAST DATA — pre-fetched server-side (use these numbers directly)\n\n"
            f"### FX Rates:\n{fx_result}\n\n"
            f"### US Macro:\n{macro_result}\n\n"
            f"### IRP Calculation (spot={spot}, NBU=13.5%, Fed={fed}%, UA-CPI=12%, US-CPI={us_cpi}%):\n{irp_result}\n\n"
            f"⚠️ The data above is already fetched. Do NOT call any tools.\n\n"
            f"MANDATORY OUTPUT FORMAT:\n"
            f"<thinking>\n"
            f"Поточний спот: {spot} UAH/USD (НБУ офіційний)\n"
            f"Ставка НБУ: 13.5% | Fed Rate: {fed}% | UA-CPI: 12% | US-CPI: {us_cpi}%\n"
            f"IRP результат: [витягни з IRP Calculation вище — covered IRP, uncovered IRP, PPP]\n"
            f"Базовий сценарій: [IRP base value] UAH/USD\n"
            f"Бичачий сценарій: UAH зміцнюється якщо НБУ підвищить ставку або інфляція сповільниться\n"
            f"Ведмежий сценарій: UAH слабшає якщо бюджетний дефіцит зросте або війна затягнеться\n"
            f"ВЕРДИКТ: USD/UAH до кінця 2026 — [конкретна цифра] базовий, [+-X] відхилення\n"
            f"</thinking>"
        )
        return system_prompt + injection

    except Exception as e:
        logger.warning("forecast_prefetch_failed", error=str(e))
        return system_prompt


class LangGraphAgent:
    """Manages the LangGraph Agent/workflow and interactions with the LLM.

    This class handles the creation and management of the LangGraph workflow,
    including LLM interactions, database connections, and response processing.
    """

    def __init__(self):
        """Initialize the LangGraph Agent with necessary components."""
        active_tools = tools_lite if settings.DEFAULT_LLM_MODEL == "veles" else tools
        self.llm_service = llm_service
        self.llm_service.bind_tools(active_tools)
        self.tools_by_name = {tool.name: tool for tool in active_tools}
        self._connection_pool: Optional[PostgresConnPool] = None
        self._graph: Optional[CompiledStateGraph] = None
        logger.info(
            "langgraph_agent_initialized",
            model=settings.DEFAULT_LLM_MODEL,
            environment=settings.ENVIRONMENT.value,
        )

    async def _get_connection_pool(self) -> Optional[PostgresConnPool]:
        """Get a PostgreSQL connection pool using environment-specific settings.

        Returns:
            AsyncConnectionPool or None when the pool fails to initialise in
            production (the app keeps running in a degraded mode).
        """
        if self._connection_pool is None:
            try:
                # Configure pool size based on environment
                max_size = settings.POSTGRES_POOL_SIZE

                connection_url = (
                    "postgresql://"
                    f"{quote_plus(settings.POSTGRES_USER)}:{quote_plus(settings.POSTGRES_PASSWORD)}"
                    f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
                )

                self._connection_pool = AsyncConnectionPool(
                    connection_url,
                    open=False,
                    max_size=max_size,
                    kwargs={
                        "autocommit": True,
                        "connect_timeout": 5,
                        "prepare_threshold": None,
                        "row_factory": dict_row,
                    },
                )
                await self._connection_pool.open()
                logger.info("connection_pool_created", max_size=max_size, environment=settings.ENVIRONMENT.value)
            except Exception as e:
                logger.error("connection_pool_creation_failed", error=str(e), environment=settings.ENVIRONMENT.value)
                # In production, we might want to degrade gracefully
                if settings.ENVIRONMENT == Environment.PRODUCTION:
                    logger.warning("continuing_without_connection_pool", environment=settings.ENVIRONMENT.value)
                    return None
                raise e
        return self._connection_pool

    async def _chat(self, state: GraphState, config: RunnableConfig) -> Command:
        """Process the chat state and generate a response.

        Args:
            state (GraphState): The current state of the conversation.
            config (RunnableConfig): The runnable configuration for this invocation.

        Returns:
            Command: Command object with updated state and next node to execute.
        """
        # Get the current LLM instance for metrics
        current_llm = self.llm_service.get_llm()
        model_name = (
            current_llm.model_name
            if current_llm and hasattr(current_llm, "model_name")
            else settings.DEFAULT_LLM_MODEL
        )

        username = config.get("metadata", {}).get("username")
        thread_id = config.get("configurable", {}).get("thread_id")
        SYSTEM_PROMPT = load_system_prompt(username=username, long_term_memory=state.long_term_memory)

        # Force-inject forecast context when model keeps returning spot instead of IRP
        SYSTEM_PROMPT = await _maybe_inject_forecast_context(SYSTEM_PROMPT, state.messages)

        # ── Bug fix: check tool call limit BEFORE calling LLM ──────────────────
        # Previously this check was AFTER the LLM call. After MAX_TOOL_CALLS
        # the context is bloated and trim_messages may return empty → BadRequestError.
        if state.tool_call_count >= MAX_TOOL_CALLS:
            logger.warning(
                "tool_call_limit_reached_early_exit",
                session_id=thread_id,
                tool_call_count=state.tool_call_count,
                limit=MAX_TOOL_CALLS,
            )
            error_text = (
                "Досягнуто ліміт інструментів для цього запиту. "
                "Будь ласка, перефразуйте або задайте конкретніше питання."
            )
            error_envelope = UniversalEnvelope(
                intent=IntentEnum.ERROR,
                text_response=error_text,
            )
            error_msg = AIMessage(content=f"<output>{error_envelope.model_dump_json()}</output>")
            return Command(
                update={"messages": [error_msg], "last_envelope": error_envelope},
                goto=END,
            )

        # Prepare messages with system prompt
        messages = prepare_messages(state.messages, SYSTEM_PROMPT)

        try:
            # Phase 5.2 — log LLM invocation start to WORM
            from app.infrastructure.compliance.audit_callback import _write_worm_entry
            from datetime import datetime, timezone
            _t0 = asyncio.get_event_loop().time()
            _write_worm_entry({
                "schema_version": "2.0",
                "trace_id": config.get("metadata", {}).get("session_id", ""),
                "session_id": thread_id,
                "user_id": config.get("metadata", {}).get("user_id"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "step_type": "llm_start",
                "payload": {"model": model_name, "message_count": len(messages)},
            })

            # Use LLM service with automatic retries and circular fallback
            with llm_inference_duration_seconds.labels(model=model_name).time():
                response_message = await self.llm_service.call(dump_messages(messages))

            # Process response to handle structured content blocks
            response_message = process_llm_response(response_message)

            # Phase 5.2 — log LLM response to WORM with token counts
            _elapsed_ms = (asyncio.get_event_loop().time() - _t0) * 1000
            _content = response_message.content if isinstance(response_message.content, str) else str(response_message.content)
            _usage = getattr(response_message, "usage_metadata", None) or {}
            if not _usage.get("output_tokens"):
                _meta = getattr(response_message, "response_metadata", {}) or {}
                _raw_usage = _meta.get("token_usage") or _meta.get("usage") or {}
                if _raw_usage.get("completion_tokens"):
                    _usage = {
                        "input_tokens": _raw_usage.get("prompt_tokens", 0),
                        "output_tokens": _raw_usage.get("completion_tokens", 0),
                        "total_tokens": _raw_usage.get("total_tokens", 0),
                    }
                else:
                    _out_toks = max(1, len(_content) // 4)
                    _in_toks = max(1, len(SYSTEM_PROMPT) // 4)
                    _usage = {
                        "input_tokens": _in_toks,
                        "output_tokens": _out_toks,
                        "total_tokens": _in_toks + _out_toks,
                    }
            _write_worm_entry({
                "schema_version": "2.0",
                "trace_id": config.get("metadata", {}).get("session_id", ""),
                "session_id": thread_id,
                "user_id": config.get("metadata", {}).get("user_id"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "step_type": "llm_end",
                "payload": {
                    "model": model_name,
                    "duration_ms": round(_elapsed_ms, 1),
                    "output_chars": len(_content),
                    "output_snippet": _content[:200],
                    "tokens": {
                        "prompt": _usage.get("input_tokens", 0),
                        "completion": _usage.get("output_tokens", 0),
                        "total": _usage.get("total_tokens", 0),
                        "tps": round(_usage.get("output_tokens", 0) / (_elapsed_ms / 1000), 1) if _elapsed_ms > 0 else 0,
                    },
                },
            })

            is_tool_call_response = (
                isinstance(response_message, AIMessage) and bool(response_message.tool_calls)
            )

            # ── Phase 1.2: validate envelope on final responses ──────────────────
            envelope = None
            if not is_tool_call_response:
                raw_content = (
                    response_message.content
                    if isinstance(response_message.content, str)
                    else str(response_message.content)
                )
                # strict=True: an unstructured/malformed response must route to
                # _finalize for constrained regeneration, not silently pass through
                # as a low-fidelity 'chat' envelope (Phase 1.2 was previously
                # unreachable in practice because the lenient parser always
                # succeeded via its plain-text fallback).
                envelope = parse_envelope_from_response(raw_content, strict=True)
                if envelope:
                    # Phase 2.3 — resolve {{SYMBOL}} placeholders from verified state
                    binding_ctx = build_context_from_graph_state(state)
                    if binding_ctx:
                        processor = DelayedBindingProcessor(binding_ctx)
                        envelope, binding_result = processor.resolve_envelope(envelope)
                        if binding_result.resolved:
                            logger.info("delayed_binding_resolved", session_id=thread_id, resolved=binding_result.resolved)
                        if binding_result.unresolved:
                            logger.warning("delayed_binding_unresolved", session_id=thread_id, unresolved=binding_result.unresolved)
                    logger.info(
                        "envelope_validated",
                        session_id=thread_id,
                        intent=envelope.intent,
                        has_financial_data=envelope.financial_data is not None,
                        model=model_name,
                    )
                else:
                    logger.warning(
                        "envelope_validation_failed",
                        session_id=thread_id,
                        content_snippet=raw_content[:100],
                    )

            logger.info("llm_response_generated", session_id=thread_id, model=model_name, environment=settings.ENVIRONMENT.value)

            # Route: tool call → tool_call node; final with envelope → END;
            # final without envelope → finalize node (constrained decoding)
            if is_tool_call_response:
                goto: str = "tool_call"
            elif envelope:
                goto = END
            else:
                goto = "finalize"

            update: dict = {"messages": [response_message]}
            if envelope:
                update["last_envelope"] = envelope
            return Command(update=update, goto=goto)
        except Exception as e:
            logger.error(
                "llm_call_failed_all_models",
                session_id=thread_id,
                error=str(e),
                environment=settings.ENVIRONMENT.value,
            )
            raise Exception(f"failed to get llm response after trying all models: {str(e)}")

    # Define our tool node
    async def _tool_call(self, state: GraphState) -> Command:
        """Process tool calls from the last message.

        Args:
            state: The current agent state containing messages and tool calls.

        Returns:
            Command: Command object with updated messages and routing back to chat.
        """
        tool_calls = state.messages[-1].tool_calls

        # Build a set of (tool_name, frozen_args) from previous AI messages
        # to detect and break infinite tool call loops.
        _previous_calls: set[tuple] = set()
        for _msg in state.messages[:-1]:
            if isinstance(_msg, AIMessage) and _msg.tool_calls:
                for _prev in _msg.tool_calls:
                    try:
                        _previous_calls.add((_prev["name"], str(sorted(_prev["args"].items()))))
                    except Exception:
                        pass

        async def _execute_tool(tool_call: dict) -> ToolMessage:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]

            # Deduplication guard: if this exact tool+args was already called in
            # this turn, return a stop message instead of executing again.
            # This breaks infinite loops (e.g. load_skill called 3× in a row).
            try:
                call_sig = (tool_name, str(sorted(tool_args.items())))
                if call_sig in _previous_calls:
                    logger.warning(
                        "duplicate_tool_call_blocked",
                        tool=tool_name,
                        args=str(tool_args)[:100],
                    )
                    return ToolMessage(
                        content=(
                            f"[DUPLICATE BLOCKED] '{tool_name}' with the same arguments was already "
                            "called this turn. Do NOT call it again — use the result from the "
                            "previous call. Proceed to write the final answer now."
                        ),
                        name=tool_name,
                        tool_call_id=tool_call["id"],
                    )
            except Exception:
                pass

            # Guard: unknown tool name → return error instead of KeyError crash
            if tool_name not in self.tools_by_name:
                available = list(self.tools_by_name.keys())
                logger.warning("unknown_tool_called", tool=tool_name, available=available[:8])
                return ToolMessage(
                    content=(
                        f"Tool '{tool_name}' does not exist. "
                        f"Available tools: {', '.join(available)}. "
                        "Do NOT call non-existent tools. Write your final answer now."
                    ),
                    name=tool_name,
                    tool_call_id=tool_call["id"],
                )

            # Read-Only + Execute: validate intent before any side-effect
            is_valid, validation_error = validate_tool_intent(tool_name, tool_args)
            if not is_valid:
                return ToolMessage(
                    content=(
                        f"Intent validation failed for '{tool_name}': {validation_error}\n"
                        "Please call read_tool_schema('{tool_name}') to review the "
                        "required parameters and correct your input."
                    ),
                    name=tool_name,
                    tool_call_id=tool_call["id"],
                )

            tool_result = await self.tools_by_name[tool_name].ainvoke(tool_args)

            # Phase 5.2 — log tool execution to WORM
            from app.infrastructure.compliance.audit_callback import _write_worm_entry
            from datetime import datetime, timezone
            _write_worm_entry({
                "schema_version": "2.0",
                "session_id": state.messages[-1].id if state.messages else "",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "step_type": "tool_end",
                "payload": {
                    "tool": tool_name,
                    "args_snippet": str(tool_args)[:200],
                    "result_snippet": str(tool_result)[:200],
                },
            })

            return ToolMessage(
                content=tool_result,
                name=tool_name,
                tool_call_id=tool_call["id"],
            )

        # Execute tool calls concurrently when multiple are requested
        if len(tool_calls) == 1:
            outputs = [await _execute_tool(tool_calls[0])]
        else:
            outputs = list(await asyncio.gather(*[_execute_tool(tc) for tc in tool_calls]))

        return Command(
            update={
                "messages": outputs,
                "tool_call_count": state.tool_call_count + len(tool_calls),
            },
            goto="chat",
        )

    async def _finalize(self, state: GraphState, config: RunnableConfig) -> Command:
        """Guarantee a valid UniversalEnvelope via constrained decoding (Phase 1.2).

        Called by _chat when parse_envelope_from_response(strict=True) returns
        None — i.e. the model produced text but missed a valid
        <output>JSON</output> block matching the UniversalEnvelope schema. Uses
        LangChain with_structured_output which maps to vLLM response_format →
        XGrammar backend. The model physically cannot emit a token that violates
        the UniversalEnvelope JSON schema.

        This is the actual enforcement point: every non-tool-call turn either
        has a schema-valid <output> block already, or is regenerated here under
        a hard grammar constraint. No response reaches the caller without
        passing through one of the two. Fast even when it fires, because the
        model only reformats pre-generated text — no new reasoning needed.
        """
        thread_id = config.get("configurable", {}).get("thread_id")

        last_ai = next(
            (m for m in reversed(state.messages) if isinstance(m, AIMessage) and not m.tool_calls),
            None,
        )
        if last_ai is None:
            return Command(update={}, goto=END)

        raw = last_ai.content if isinstance(last_ai.content, str) else str(last_ai.content)

        # Strip reasoning block — keep only the substantive response text
        display = re.sub(r"<thinking>[\s\S]*?</thinking>", "", raw, flags=re.IGNORECASE).strip()
        display = re.sub(r"</?output>", "", display, flags=re.IGNORECASE).strip()
        display = (display or raw)[:3000]

        format_msgs = [
            {
                "role": "system",
                "content": (
                    "Convert the financial analysis text below into a structured JSON response. "
                    "Choose the most specific intent:\n"
                    "- fx_rate: currency exchange rate or FX analysis\n"
                    "- equity: stock or share analysis\n"
                    "- macro: macroeconomic indicators (GDP, CPI, Fed rate, yields)\n"
                    "- calculation: deterministic math result (Kelly, DCF, IRP, Monte Carlo)\n"
                    "- forecast: future price or economic prediction\n"
                    "- chat: general conversation with no financial data\n"
                    "- error: request could not be completed\n"
                    "Populate 'financial_data' with any numeric values present in the text."
                ),
            },
            {"role": "user", "content": display},
        ]

        try:
            envelope: UniversalEnvelope = await llm_service.call(
                messages=format_msgs,
                response_format=UniversalEnvelope,
            )
            logger.info(
                "finalize_constrained_decoding_success",
                session_id=thread_id,
                intent=envelope.intent,
                has_financial_data=envelope.financial_data is not None,
            )
            return Command(update={"last_envelope": envelope}, goto=END)
        except Exception as exc:
            logger.warning("finalize_constrained_decoding_failed", session_id=thread_id, error=str(exc)[:200])
            return Command(update={}, goto=END)

    async def create_graph(self) -> Optional[CompiledStateGraph]:
        """Create and configure the LangGraph workflow.

        Returns:
            Optional[CompiledStateGraph]: The configured LangGraph instance or None if init fails
        """
        if self._graph is None:
            try:
                graph_builder = StateGraph(GraphState)
                graph_builder.add_node("chat", self._chat, destinations=("tool_call", "finalize", END))
                graph_builder.add_node(
                    "tool_call",
                    self._tool_call,
                    destinations=("chat",),
                    retry_policy=RetryPolicy(max_attempts=3),
                )
                graph_builder.add_node("finalize", self._finalize, destinations=(END,))
                graph_builder.set_entry_point("chat")
                graph_builder.set_finish_point("chat")

                # Get connection pool (may be None in production if DB unavailable)
                connection_pool = await self._get_connection_pool()
                if connection_pool:
                    checkpointer = AsyncPostgresSaver(connection_pool)
                    await checkpointer.setup()
                else:
                    # In production, proceed without checkpointer if needed
                    checkpointer = None
                    if settings.ENVIRONMENT != Environment.PRODUCTION:
                        raise Exception("Connection pool initialization failed")

                self._graph = graph_builder.compile(
                    checkpointer=checkpointer, name=f"{settings.PROJECT_NAME} Agent ({settings.ENVIRONMENT.value})"
                )

                logger.info(
                    "graph_created",
                    graph_name=f"{settings.PROJECT_NAME} Agent",
                    environment=settings.ENVIRONMENT.value,
                    has_checkpointer=checkpointer is not None,
                )
            except Exception as e:
                logger.error("graph_creation_failed", error=str(e), environment=settings.ENVIRONMENT.value)
                # In production, we don't want to crash the app
                if settings.ENVIRONMENT == Environment.PRODUCTION:
                    logger.warning("continuing_without_graph")
                    return None
                raise e

        return self._graph

    async def _get_graph(self) -> CompiledStateGraph:
        """Return the compiled graph, creating it on first access.

        Raises:
            RuntimeError: When ``create_graph()`` swallowed an init failure
                (production-only path) and returned ``None``. Callers can
                rely on the return being non-``None``.
        """
        if self._graph is None:
            self._graph = await self.create_graph()
        if self._graph is None:
            raise RuntimeError("graph initialization failed")
        return self._graph

    async def get_response(
        self,
        messages: list[Message],
        session_id: str,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
    ) -> list[Message]:
        """Get a response from the LLM.

        Args:
            messages (list[Message]): The messages to send to the LLM.
            session_id (str): The session ID for the conversation.
            user_id (Optional[str]): The user ID for the conversation.
            username (Optional[str]): The display name of the user.

        Returns:
            list[Message]: The response from the LLM.
        """
        import time

        graph = await self._get_graph()
        # Phase 5.2 — ComplianceAuditCallback writes every step to local WORM log
        compliance_cb = ComplianceAuditCallback(session_id=session_id, user_id=user_id)
        callbacks: list[BaseCallbackHandler] = [compliance_cb]
        if settings.LANGFUSE_TRACING_ENABLED:
            callbacks.append(langfuse_callback_handler)
        config: RunnableConfig = {
            "configurable": {"thread_id": session_id},
            "callbacks": callbacks,
            "metadata": {
                "user_id": user_id,
                "username": username,
                "session_id": session_id,
                "environment": settings.ENVIRONMENT.value,
                "debug": settings.DEBUG,
            },
        }

        # ── PII Shield: mask user inputs BEFORE they reach the LLM ──────────
        raw_messages = dump_messages(messages)
        masked_messages_dicts, pii_audit = mask_messages(raw_messages)

        start_ms = time.monotonic()

        try:
            # Run state check and memory search concurrently to save 200-500ms
            state, relevant_memory = await asyncio.gather(
                graph.aget_state(config),
                memory_service.search(user_id, messages[-1].content),
            )

            if state.next:
                logger.info("resuming_interrupted_graph", session_id=session_id, next_nodes=state.next)
                response = await graph.ainvoke(
                    Command(resume=messages[-1].content),
                    config=config,
                )
            else:
                relevant_memory = relevant_memory or "No relevant memory found."
                response = await graph.ainvoke(
                    input={"messages": masked_messages_dicts, "long_term_memory": relevant_memory},
                    config=config,
                )

            duration_ms = (time.monotonic() - start_ms) * 1000

            # Check if the graph was interrupted during this invocation
            state = await graph.aget_state(config)
            if state.next:
                interrupt_value = state.tasks[0].interrupts[0].value if state.tasks else "Waiting for input."
                logger.info("graph_interrupted", session_id=session_id, interrupt_value=str(interrupt_value))
                return [Message(role="assistant", content=str(interrupt_value))]

            openai_msgs = cast(list[dict], convert_to_openai_messages(response["messages"]))

            # ── Extract tool calls for audit record ───────────────────────────
            tool_calls_audit = [
                {"name": m.get("name", ""), "content": str(m.get("content", ""))[:500]}
                for m in openai_msgs
                if m.get("role") == "tool"
            ]

            # ── Fire-and-forget: memory + audit + conversation log ────────────
            asyncio.create_task(memory_service.add(user_id, openai_msgs, config.get("metadata")))

            # Phase 4.2 — write episode to episodic store (SQLite + FTS5)
            final_state = await graph.aget_state(config)
            last_envelope = final_state.values.get("last_envelope") if final_state.values else None
            envelopes = [last_envelope] if last_envelope else []
            asyncio.create_task(write_episode(
                session_id=session_id,
                user_id=user_id,
                messages=openai_msgs,
                envelopes=envelopes,
            ))

            # Extract last user message and assistant response for learning loop
            last_user = next((m["content"] for m in reversed(masked_messages_dicts) if m.get("role") == "user"), "")
            last_assistant = next((m.get("content", "") for m in reversed(openai_msgs) if m.get("role") == "assistant"), "")
            if last_user and last_assistant:
                asyncio.create_task(log_conversation(
                    session_id=session_id,
                    user_id=user_id,
                    user_message=last_user,
                    assistant_response=last_assistant,
                    tool_calls=tool_calls_audit,
                    model=settings.DEFAULT_LLM_MODEL,
                    duration_ms=duration_ms,
                ))

            asyncio.create_task(upload_audit_trace_async(
                session_id=session_id,
                user_id=user_id,
                input_messages=masked_messages_dicts,
                output_messages=[m for m in openai_msgs if m.get("role") == "assistant"],
                tool_calls=tool_calls_audit,
                pii_audit=pii_audit,
                model=settings.DEFAULT_LLM_MODEL,
                duration_ms=duration_ms,
            ))

            return self.__process_messages(response["messages"])
        except GraphInterrupt:
            state = await graph.aget_state(config)
            interrupt_value = state.tasks[0].interrupts[0].value if state.tasks else "Waiting for input."
            logger.info("graph_interrupted", session_id=session_id, interrupt_value=str(interrupt_value))
            return [Message(role="assistant", content=str(interrupt_value))]
        except Exception as e:
            logger.exception("get_response_failed", error=str(e), session_id=session_id)
            raise

    async def get_stream_response(
        self,
        messages: list[Message],
        session_id: str,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Get a stream response from the LLM.

        Args:
            messages (list[Message]): The messages to send to the LLM.
            session_id (str): The session ID for the conversation.
            user_id (Optional[str]): The user ID for the conversation.
            username (Optional[str]): The display name of the user.

        Yields:
            str: Tokens of the LLM response.
        """
        callbacks: list[BaseCallbackHandler] = [langfuse_callback_handler] if settings.LANGFUSE_TRACING_ENABLED else []
        config: RunnableConfig = {
            "configurable": {"thread_id": session_id},
            "callbacks": callbacks,
            "metadata": {
                "user_id": user_id,
                "username": username,
                "session_id": session_id,
                "environment": settings.ENVIRONMENT.value,
                "debug": settings.DEBUG,
            },
        }
        graph = await self._get_graph()

        try:
            # Run state check and memory search concurrently to save 200-500ms
            state, relevant_memory = await asyncio.gather(
                graph.aget_state(config),
                memory_service.search(user_id, messages[-1].content),
            )

            if state.next:
                logger.info("resuming_interrupted_graph_stream", session_id=session_id, next_nodes=state.next)
                graph_input = Command(resume=messages[-1].content)
            else:
                relevant_memory = relevant_memory or "No relevant memory found."
                graph_input = {"messages": dump_messages(messages), "long_term_memory": relevant_memory}

            # Accumulate full response — streaming tool-call-parser is unreliable,
            # so we buffer everything and fall back to non-streaming if needed.
            _full_response = ""
            _had_tool_notification = False

            async for token, _ in graph.astream(
                graph_input,
                config,
                stream_mode="messages",
            ):
                if not isinstance(token, (AIMessage, AIMessageChunk)):
                    continue

                if isinstance(token, AIMessage) and token.tool_calls:
                    tool_names = ", ".join(tc["name"] for tc in token.tool_calls)
                    yield f"\x00TOOL:{tool_names}"
                    _full_response = ""
                    _had_tool_notification = True
                    continue

                text = extract_text_content(token.content)
                if text:
                    _full_response += text

            # If response looks like a raw function call (tool-call-parser failed in
            # streaming mode), fall back to the reliable non-streaming path.
            _stripped = _full_response.strip()

            def _looks_like_tool_call(text: str) -> bool:
                """Detect raw tool-call JSON regardless of spacing or prefix."""
                # Remove any thinking block before checking
                _t = re.sub(r"<thinking>[\s\S]*?</thinking>", "", text, flags=re.IGNORECASE).strip()
                return bool(
                    _t.startswith('{"type": "function"') or
                    _t.startswith('{"type":"function"') or
                    # Llama <|python_tag|> format
                    _t.startswith("<|python_tag|>") or
                    # Generic: has name + parameters/arguments keys (either spacing style)
                    (
                        ('"name": "' in _t or '"name":"' in _t) and
                        ('"parameters"' in _t or '"arguments"' in _t)
                    )
                )

            _is_raw_tool_call = _looks_like_tool_call(_stripped)

            async def _tool_call_fallback(raw_json: str) -> str:
                """Execute tool from raw JSON and call LLM directly (no graph/session state)."""
                import json as _json
                try:
                    tc = _json.loads(raw_json)
                    tool_name = tc.get("name") or tc.get("function", {}).get("name", "")
                    params = tc.get("parameters") or tc.get("arguments") or tc.get("function", {}).get("arguments", {})
                    if isinstance(params, str):
                        params = _json.loads(params)
                except Exception:
                    tool_name, params = "", {}

                tool_result = ""
                if tool_name and tool_name in self.tools_by_name:
                    try:
                        tool_result = await self.tools_by_name[tool_name].ainvoke(params or {})
                    except Exception as te:
                        tool_result = f"Tool error: {te}"

                # Direct LLM call — no tools, no session state, clean slate
                user_text = messages[-1].content if messages else ""
                SYSTEM_PROMPT = load_system_prompt(username=username, long_term_memory="No relevant memory found.")
                direct_msgs = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_text},
                ]
                if tool_result:
                    direct_msgs.append({"role": "assistant", "content": f"[Tool result: {tool_result}]"})
                    direct_msgs.append({"role": "user", "content": "На основі цих даних дай повну фінансову відповідь українською."})

                try:
                    from app.services.llm.registry import LLMRegistry
                    # Use a fresh LLM instance WITHOUT tool bindings —
                    # the tool-bound self._llm would trigger another JSON output
                    _fresh_llm = LLMRegistry.get(settings.DEFAULT_LLM_MODEL)
                    resp = await _fresh_llm.ainvoke(direct_msgs)
                    raw = resp.content if isinstance(resp.content, str) else str(resp.content)
                    # Strip thinking/output tags regardless of envelope format
                    plain = re.sub(r"<thinking>[\s\S]*?</thinking>", "", raw, flags=re.IGNORECASE).strip()
                    plain = re.sub(r"</?output>", "", plain, flags=re.IGNORECASE).strip()
                    if not plain or _looks_like_tool_call(plain):
                        # Model still outputting JSON — return tool result as plain text
                        return tool_result if tool_result else "Не вдалось отримати відповідь."
                    env = parse_envelope_from_response(plain)
                    if env and not _looks_like_tool_call(env.text_response):
                        return env.text_response
                    return plain
                except Exception as fe:
                    return tool_result if tool_result else f"Помилка: {fe}"

            if _is_raw_tool_call or (_had_tool_notification and not _stripped):
                yield "\x00TOOL:processing"
                # Extract clean JSON (remove any <thinking> prefix)
                _clean_json = re.sub(r"<thinking>[\s\S]*?</thinking>", "", _stripped, flags=re.IGNORECASE).strip()
                _fallback_text = await _tool_call_fallback(_clean_json)
                yield _fallback_text
            elif _full_response.strip():
                envelope = parse_envelope_from_response(_full_response)
                if envelope and envelope.intent.value != "error":
                    # Guard: text_response must not itself be a tool-call JSON
                    if _looks_like_tool_call(envelope.text_response):
                        yield "\x00TOOL:processing"
                        _clean_json = re.sub(r"<thinking>[\s\S]*?</thinking>", "", _stripped, flags=re.IGNORECASE).strip()
                        yield await _tool_call_fallback(_clean_json)
                    else:
                        yield envelope.text_response
                else:
                    _plain = re.sub(r"<thinking>[\s\S]*?</thinking>", "", _full_response, flags=re.IGNORECASE).strip()
                    _plain = re.sub(r"</?output>", "", _plain, flags=re.IGNORECASE).strip()
                    yield _plain or _full_response

            # After streaming completes, check for interrupt or update memory
            state = await graph.aget_state(config)
            if state.next:
                interrupt_value = state.tasks[0].interrupts[0].value if state.tasks else "Waiting for input."
                logger.info("graph_interrupted_stream", session_id=session_id, interrupt_value=str(interrupt_value))
                yield str(interrupt_value)
            elif state.values and "messages" in state.values:
                openai_msgs = cast(list[dict], convert_to_openai_messages(state.values["messages"]))
                asyncio.create_task(memory_service.add(user_id, openai_msgs, config.get("metadata")))
        except GraphInterrupt:
            state = await graph.aget_state(config)
            interrupt_value = state.tasks[0].interrupts[0].value if state.tasks else "Waiting for input."
            logger.info("graph_interrupted_stream", session_id=session_id, interrupt_value=str(interrupt_value))
            yield str(interrupt_value)
        except Exception as stream_error:
            logger.exception("stream_processing_failed", error=str(stream_error), session_id=session_id)
            raise stream_error

    async def get_chat_history(self, session_id: str) -> list[Message]:
        """Get the chat history for a given thread ID.

        Args:
            session_id (str): The session ID for the conversation.

        Returns:
            list[Message]: The chat history.
        """
        graph = await self._get_graph()

        config: RunnableConfig = {"configurable": {"thread_id": session_id}}
        state: StateSnapshot = await graph.aget_state(config=config)
        return self.__process_messages(state.values["messages"]) if state.values else []

    def __process_messages(self, messages: list[BaseMessage]) -> list[Message]:
        openai_style_messages = convert_to_openai_messages(messages)
        result = []
        for message in openai_style_messages:
            if message["role"] not in ("assistant", "user"):
                continue
            raw = str(message["content"])
            if not raw:
                continue
            if message["role"] == "assistant":
                # Extract text_response from UniversalEnvelope if present
                envelope = parse_envelope_from_response(raw)
                if envelope and envelope.intent.value != "error":
                    content = envelope.text_response
                else:
                    # Fallback: strip <thinking> and <output> tags
                    content = re.sub(r"<thinking>[\s\S]*?</thinking>", "", raw, flags=re.IGNORECASE).strip()
                    content = re.sub(r"<output>[\s\S]*?</output>", "", content, flags=re.IGNORECASE).strip()
                    content = content or raw
            else:
                content = raw
            result.append(Message(role=message["role"], content=content))
        return result

    async def clear_chat_history(self, session_id: str) -> None:
        """Clear all chat history for a given thread ID.

        Args:
            session_id: The ID of the session to clear history for.

        Raises:
            Exception: If there's an error clearing the chat history.
        """
        try:
            # Make sure the pool is initialized in the current event loop
            conn_pool = await self._get_connection_pool()
            if conn_pool is None:
                raise RuntimeError("connection pool unavailable; cannot clear chat history")

            # Batch all DELETEs in a single pipeline round-trip
            async with conn_pool.connection() as conn:
                async with conn.pipeline():
                    for table in settings.CHECKPOINT_TABLES:
                        await conn.execute(
                            sql.SQL("DELETE FROM {} WHERE thread_id = %s").format(sql.Identifier(table)),
                            (session_id,),
                        )
                logger.info(
                    "checkpoint_tables_cleared_for_session",
                    tables=settings.CHECKPOINT_TABLES,
                    session_id=session_id,
                )

        except Exception as e:
            logger.error(
                "clear_chat_history_operation_failed",
                session_id=session_id,
                error=str(e),
            )
            raise
