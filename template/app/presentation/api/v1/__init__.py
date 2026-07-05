"""Presentation — API v1 re-exports (Strangler Fig adapter).

New code: from app.presentation.api.v1 import chatbot_router, auth_router
"""
from app.api.v1.api import api_router
from app.api.v1.auth import router as auth_router
from app.api.v1.chatbot import router as chatbot_router

__all__ = ["api_router", "auth_router", "chatbot_router"]
