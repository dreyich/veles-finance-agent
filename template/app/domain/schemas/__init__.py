"""Domain schemas — re-exports from app.schemas (Strangler Fig adapter).

New code should import from here:
    from app.domain.schemas import UniversalEnvelope, IntentEnum, GraphState

Old code continues to import from app.schemas without any changes.
Physical file migration happens incrementally as modules are refactored.
"""
from app.schemas import (
    AnalyzeRequest,
    BaseResponse,
    ChatRequest,
    ChatResponse,
    DDReport,
    GraphState,
    Message,
    StreamResponse,
    Token,
    Verdict,
)
from app.schemas.envelope import FinancialData, IntentEnum, UniversalEnvelope

__all__ = [
    # Core message types
    "Message",
    "ChatRequest",
    "ChatResponse",
    "StreamResponse",
    # Auth
    "Token",
    "BaseResponse",
    # Graph
    "GraphState",
    # Reports
    "DDReport",
    "AnalyzeRequest",
    "Verdict",
    # Phase 1.1 — Universal Envelope
    "IntentEnum",
    "FinancialData",
    "UniversalEnvelope",
]
