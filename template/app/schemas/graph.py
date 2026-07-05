"""This file contains the graph schema for the application."""

from typing import Annotated, Optional

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from app.schemas.envelope import UniversalEnvelope


MAX_TOOL_CALLS = 10  # Hard cap — prevents infinite tool-call loops (token burning)


class GraphState(BaseModel):
    """State definition for the LangGraph Agent/Workflow."""

    messages: Annotated[list, add_messages] = Field(
        default_factory=list, description="The messages in the conversation"
    )
    long_term_memory: str = Field(default="", description="The long term memory of the conversation")
    current_ticker: Optional[str] = Field(default=None, description="The currently active stock/asset ticker symbol")
    portfolio_balance: Optional[float] = Field(default=None, description="User's current portfolio balance in USD")
    risk_profile: Optional[str] = Field(
        default=None, description="User's risk tolerance: 'conservative', 'moderate', or 'aggressive'"
    )
    # Loop guard — incremented on every tool call, hard-capped at MAX_TOOL_CALLS
    tool_call_count: int = Field(default=0, description="Number of tool calls made in this turn")
    # Phase 1.2 — validated structured output from the last LLM final response
    last_envelope: Optional[UniversalEnvelope] = Field(
        default=None,
        description="Validated UniversalEnvelope from the most recent non-tool-call LLM response",
    )
