"""Infrastructure — LLM provider (vLLM / OpenAI-compatible).

Re-exports from app.services.llm (Strangler Fig adapter).
New code: from app.infrastructure.llm import llm_service, LLMService, LLMRegistry
"""
from app.services.llm import llm_service
from app.services.llm.registry import LLMRegistry
from app.services.llm.service import LLMService

__all__ = ["LLMService", "LLMRegistry", "llm_service"]
