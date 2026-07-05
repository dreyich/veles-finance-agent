"""Delayed Binding Processor — Phase 2.3.

Prevents LLM hallucination of sensitive financial parameters by using
symbolic placeholders that are resolved server-side from verified context.

How it works:
  1. LLM outputs {{SYMBOL}} for values it should not fabricate.
  2. After envelope parsing, DelayedBindingProcessor substitutes real values
     from the verified session context (GraphState, user profile, live data).
  3. Unresolved symbols are reported so callers can decide how to handle them.

Example LLM output (before resolution):
  "Your portfolio of {{USER_PORTFOLIO_BALANCE}} USD has grown..."

After resolution with context = {"USER_PORTFOLIO_BALANCE": "12500.00"}:
  "Your portfolio of 12500.00 USD has grown..."

This pattern is especially critical for SEC Rule 17a-3 compliance (Phase 5):
  - Never log fabricated financial values as if they were real
  - Audit trail must show which values came from verified sources
"""

import re
from dataclasses import dataclass, field
from typing import Any, Optional

# Matches {{SYMBOL}} or {{SYMBOL_WITH_UNDERSCORES}}
_SYMBOL_RE = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")


@dataclass
class BindingResult:
    """Result of a delayed binding resolution pass."""

    text: str
    resolved: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        """True when all symbols were successfully resolved."""
        return len(self.unresolved) == 0

    @property
    def has_symbols(self) -> bool:
        """True when the original text contained ANY symbols."""
        return bool(self.resolved) or bool(self.unresolved)


class DelayedBindingProcessor:
    """Resolves {{SYMBOL}} placeholders in LLM output text.

    Context keys must be UPPER_SNAKE_CASE strings matching the symbol names.
    Values are converted to str before substitution.

    Usage:
        context = {
            "USER_PORTFOLIO_BALANCE": "12500.00",
            "USER_RISK_PROFILE": "moderate",
            "SPOT_RATE_UAH": "44.92",
        }
        processor = DelayedBindingProcessor(context)
        result = processor.resolve("Your balance is {{USER_PORTFOLIO_BALANCE}} USD.")
        # result.text == "Your balance is 12500.00 USD."
        # result.resolved == ["USER_PORTFOLIO_BALANCE"]
        # result.unresolved == []
    """

    # Built-in symbols that are NEVER allowed to be resolved from LLM context
    # (must come from verified server-side sources only).
    PROTECTED_SYMBOLS = frozenset({
        "ACCOUNT_NUMBER",
        "SSN",
        "TAX_ID",
        "ROUTING_NUMBER",
        "CARD_NUMBER",
        "TRANSACTION_ID",
    })

    def __init__(self, context: dict[str, Any]):
        """Initialise with a context dict of verified server-side values."""
        self._context = {k.upper(): str(v) for k, v in context.items()}

    def resolve(self, text: str) -> BindingResult:
        """Resolve all {{SYMBOL}} placeholders in text.

        Protected symbols are never resolved — they are left as-is and added
        to the unresolved list so callers can handle them explicitly.
        """
        if not text:
            return BindingResult(text=text)

        resolved: list[str] = []
        unresolved: list[str] = []

        def _replace(match: re.Match) -> str:
            symbol = match.group(1).upper()
            if symbol in self.PROTECTED_SYMBOLS:
                unresolved.append(symbol)
                return match.group(0)
            if symbol in self._context:
                resolved.append(symbol)
                return self._context[symbol]
            unresolved.append(symbol)
            return match.group(0)

        resolved_text = _SYMBOL_RE.sub(_replace, text)
        return BindingResult(text=resolved_text, resolved=resolved, unresolved=unresolved)

    def resolve_envelope(self, envelope: Any) -> tuple[Any, BindingResult]:
        """Resolve bindings in a UniversalEnvelope's text_response.

        Returns (modified_envelope, binding_result).
        The envelope is mutated in place (text_response updated).
        financial_data fields are NOT resolved — they must come from tools.
        """
        result = self.resolve(envelope.text_response)
        if result.has_symbols:
            envelope.text_response = result.text
        return envelope, result


def build_context_from_graph_state(state: Any) -> dict[str, Any]:
    """Extract binding context from GraphState fields.

    Converts typed state fields into a flat symbol dict the processor can use.
    Add new symbols here as new state fields are introduced.
    """
    context: dict[str, Any] = {}

    if state.current_ticker:
        context["CURRENT_TICKER"] = state.current_ticker

    if state.portfolio_balance is not None:
        context["USER_PORTFOLIO_BALANCE"] = f"{state.portfolio_balance:,.2f}"

    if state.risk_profile:
        context["USER_RISK_PROFILE"] = state.risk_profile

    return context
