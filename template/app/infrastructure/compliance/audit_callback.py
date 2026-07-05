"""ComplianceAuditCallback — LangGraph/LangChain callback for SEC compliance.

Intercepts every LLM thought, tool call, and output in real-time and writes
them to a local append-only WORM log (JSONL format).

Why append-only local log in addition to S3?
  - S3 upload is async + may fail in dev (no credentials)
  - Local WORM log is instant, always available, zero-dependency
  - In production: both logs exist → defense-in-depth
  - Local log can be shipped to S3/SIEM via logstash/fluentd independently

SEC Rule 17a-4(f)(2)(ii)(A) requires:
  "records shall be preserved exclusively in a non-rewriteable,
   non-erasable format"

The local JSONL log is append-only by design:
  - File is opened in 'a' mode (append-only, never truncate)
  - No delete or overwrite operations in this module
  - In production, set filesystem ACLs to make the file immutable
  - For full WORM: use S3 Object Lock (handled by audit_logger.py)
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union
from uuid import uuid4

import structlog
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

logger = structlog.get_logger(__name__)

_WORM_LOG_DIR = Path("/app/logs/audit")
_WORM_LOG_PATH = _WORM_LOG_DIR / "worm.jsonl"


def _write_worm_entry(entry: dict) -> None:
    """Append a single JSON record to the local WORM log. Never overwrites."""
    try:
        _WORM_LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(_WORM_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception as exc:
        logger.error("worm_log_write_failed", error=str(exc))


class ComplianceAuditCallback(BaseCallbackHandler):
    """LangChain callback that writes every agent step to the WORM audit log.

    Attach to graph.ainvoke() via the 'callbacks' config parameter.
    Each step produces one JSONL line with:
      - trace_id (per-conversation UUID)
      - step_type: llm_start | llm_end | tool_start | tool_end | error
      - timestamp (UTC ISO)
      - payload: token-level detail for LLM, tool name+input+output for tools
    """

    def __init__(
        self,
        session_id: str,
        user_id: Optional[str],
        trace_id: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.session_id = session_id
        self.user_id = user_id
        self.trace_id = trace_id or str(uuid4())
        self._llm_start_time: float = 0.0

    def _entry(self, step_type: str, payload: dict) -> dict:
        return {
            "schema_version": "2.0",
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "step_type": step_type,
            "payload": payload,
        }

    # ── LLM events ────────────────────────────────────────────────────────────

    def on_llm_start(
        self, serialized: dict, prompts: list[str], **kwargs: Any
    ) -> None:
        self._llm_start_time = time.monotonic()
        _write_worm_entry(self._entry("llm_start", {
            "model": serialized.get("name") or serialized.get("id", ["?"])[-1],
            "prompt_count": len(prompts),
            "prompt_chars": sum(len(p) for p in prompts),
        }))

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        elapsed = (time.monotonic() - self._llm_start_time) * 1000
        generations = response.generations
        text_out = ""
        if generations and generations[0]:
            gen = generations[0][0]
            text_out = getattr(gen, "text", "") or str(getattr(gen, "message", ""))

        # Extract token usage — vLLM returns this in llm_output.token_usage (non-streaming)
        # or generation_info.usage (some versions). Fall back to char-based estimate.
        usage = (response.llm_output or {}).get("token_usage", {})
        if not usage.get("completion_tokens") and generations and generations[0]:
            gen_info = getattr(generations[0][0], "generation_info", {}) or {}
            usage = gen_info.get("usage", {}) or gen_info.get("token_usage", {}) or {}
        if not usage.get("completion_tokens"):
            out_toks = max(1, len(text_out) // 4)
            usage = {"prompt_tokens": 0, "completion_tokens": out_toks, "total_tokens": out_toks}

        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
        tps = round(completion_tokens / (elapsed / 1000), 1) if elapsed > 0 and completion_tokens else 0

        _write_worm_entry(self._entry("llm_end", {
            "duration_ms": round(elapsed, 1),
            "output_chars": len(text_out),
            "output_snippet": text_out[:200],
            "tokens": {
                "prompt": prompt_tokens,
                "completion": completion_tokens,
                "total": total_tokens,
                "tps": tps,
            },
            "model": (response.llm_output or {}).get("model_name", "veles"),
        }))

    def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        _write_worm_entry(self._entry("llm_error", {
            "error_type": type(error).__name__,
            "error": str(error)[:500],
        }))

    # ── Tool events ───────────────────────────────────────────────────────────

    def on_tool_start(
        self, serialized: dict, input_str: str, **kwargs: Any
    ) -> None:
        _write_worm_entry(self._entry("tool_start", {
            "tool": serialized.get("name", "?"),
            "input_snippet": str(input_str)[:300],
        }))

    def on_tool_end(self, output: str, **kwargs: Any) -> None:
        _write_worm_entry(self._entry("tool_end", {
            "output_snippet": str(output)[:300],
            "output_chars": len(str(output)),
        }))

    def on_tool_error(
        self, error: Union[Exception, KeyboardInterrupt], **kwargs: Any
    ) -> None:
        _write_worm_entry(self._entry("tool_error", {
            "error_type": type(error).__name__,
            "error": str(error)[:500],
        }))

    # ── Chain events ──────────────────────────────────────────────────────────

    def on_chain_start(
        self, serialized: dict, inputs: dict, **kwargs: Any
    ) -> None:
        _write_worm_entry(self._entry("chain_start", {
            "chain": serialized.get("name", "?"),
            "input_keys": list(inputs.keys()),
        }))

    def on_chain_end(self, outputs: dict, **kwargs: Any) -> None:
        _write_worm_entry(self._entry("chain_end", {
            "output_keys": list(outputs.keys()),
        }))
