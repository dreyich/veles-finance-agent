"""Use Cases — LangGraph agent workflow.

Re-exports from app.core.langgraph.graph (Strangler Fig adapter).
New code: from app.use_cases.agent_graph import LangGraphAgent
"""
from app.core.langgraph.graph import LangGraphAgent

__all__ = ["LangGraphAgent"]
