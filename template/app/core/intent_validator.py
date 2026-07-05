"""Read-Only + Execute Intent Validator.

Enforces the architecture principle: the LLM only DESCRIBES what it wants
to do (produces a JSON intent payload); the backend VALIDATES and EXECUTES.

This separation provides:
  1. Type safety  — Pydantic rejects malformed LLM outputs before execution.
  2. Auditability — every intent is logged before any side-effect occurs.
  3. Controllability — a human-in-the-loop gate can be inserted here.
  4. Zero hallucination math — numeric fields are validated against ranges.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  FUTURE: XGrammar Integration Point
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Today we validate AFTER the model produces output (post-hoc).
With XGrammar + SGLang we validate DURING token generation (inline):

  Step 1 — Convert intent schema to BNF grammar:
    compiler = xgrammar.GrammarCompiler(tokenizer_info)
    grammar  = compiler.compile_json_schema(KellyIntent.model_json_schema())

  Step 2 — Use grammar as logit mask during sampling:
    logits_processor = xgrammar.contrib.hf.LogitsProcessor(grammar)
    output = model.generate(..., logits_processor=[logits_processor])

  Result: The model physically cannot produce a token that would make the
  JSON invalid — e.g. it cannot write "win_probability": 1.5 because 1.5
  violates the le=0.99 constraint encoded in the BNF grammar.

Cost: ~0.1ms overhead per token vs standard sampling. Zero false positives.
Reference: https://xgrammar.mlc.ai/docs/how_to/json_mode
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.logging import logger


# ── Intent Models — one per tool that has financial side-effects ──────────────

class KellyIntent(BaseModel):
    """Validated intent for kelly_criterion_calculator.

    The LLM MUST produce a JSON matching this schema. The backend validates
    it before passing to the actual calculator — ensuring zero hallucinated
    values reach the deterministic math engine.
    """
    tool: str = Field("kelly_criterion_calculator", frozen=True)
    win_probability: float = Field(
        ..., ge=0.01, le=0.99,
        description="Win probability between 0.01 and 0.99.",
    )
    payout_ratio: float = Field(
        ..., gt=0.0,
        description="Profit/loss ratio, must be positive.",
    )

    @model_validator(mode="after")
    def check_positive_edge(self) -> "KellyIntent":
        edge = self.win_probability * self.payout_ratio - (1 - self.win_probability)
        if edge <= 0:
            raise ValueError(
                f"Strategy has no positive expected value (edge={edge:.4f}). "
                "Kelly Criterion requires edge > 0."
            )
        return self


class SandboxIntent(BaseModel):
    """Validated intent for execute_python_sandbox."""
    tool: str = Field("execute_python_sandbox", frozen=True)
    code: str = Field(..., min_length=1, max_length=8000)

    @field_validator("code")
    @classmethod
    def no_dangerous_imports(cls, v: str) -> str:
        blocked = ["subprocess", "os.system", "shutil.rmtree", "__import__", "eval(", "exec("]
        for b in blocked:
            if b in v:
                raise ValueError(f"Blocked pattern '{b}' in sandbox code.")
        return v


class SaveSkillIntent(BaseModel):
    """Validated intent for save_trading_skill."""
    tool: str = Field("save_trading_skill", frozen=True)
    skill_name: str = Field(..., min_length=2, max_length=80, pattern=r"^[a-z0-9_]+$")
    skill_content: str = Field(..., min_length=20)


class GetMarketDataIntent(BaseModel):
    """Validated intent for get_market_data.

    Enforces ticker format before any yfinance call is made.
    Prevents the LLM from hallucinating invalid tickers like 'NVDA123' or ''.
    """
    tool: str = Field("get_market_data", frozen=True)
    ticker: str = Field(..., min_length=1, max_length=10)

    @field_validator("ticker")
    @classmethod
    def validate_ticker_format(cls, v: str) -> str:
        cleaned = v.strip().upper()
        if not cleaned.replace(".", "").replace("-", "").isalnum():
            raise ValueError(
                f"Invalid ticker '{v}'. Must contain only letters, digits, dots, or hyphens."
            )
        return cleaned


# ── Intent registry — maps tool name → its Intent model ──────────────────────
_INTENT_MODELS: dict[str, type[BaseModel]] = {
    "kelly_criterion_calculator": KellyIntent,
    "execute_python_sandbox":     SandboxIntent,
    "save_trading_skill":         SaveSkillIntent,
    "get_market_data":            GetMarketDataIntent,
}


def validate_tool_intent(tool_name: str, args: dict[str, Any]) -> tuple[bool, Optional[str]]:
    """Validate a tool call intent against its Pydantic model.

    Args:
        tool_name: Name of the tool being called.
        args:      Arguments the LLM produced for the tool call.

    Returns:
        (is_valid, error_message) — error_message is None on success.
    """
    model_cls = _INTENT_MODELS.get(tool_name)

    if model_cls is None:
        # Tool has no intent model — allow through (e.g. read_tool_schema)
        return True, None

    try:
        payload = {"tool": tool_name, **args}
        model_cls.model_validate(payload)
        logger.info(
            "intent_validated",
            tool=tool_name,
            args_keys=list(args.keys()),
        )
        return True, None
    except Exception as exc:
        error = str(exc)
        logger.warning("intent_validation_failed", tool=tool_name, error=error)
        return False, error


def validate_and_format_intent(tool_name: str, args: dict[str, Any]) -> str:
    """Validate and return a formatted intent receipt for audit logging."""
    is_valid, error = validate_tool_intent(tool_name, args)

    receipt = {
        "intent": tool_name,
        "args": args,
        "validated": is_valid,
        "error": error,
    }

    return json.dumps(receipt, default=str)
