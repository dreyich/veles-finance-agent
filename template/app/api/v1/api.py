"""API v1 router configuration."""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.chatbot import router as chatbot_router
from app.api.v1.feedback import router as feedback_router
from app.core.logging import logger

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["Auth"])
api_router.include_router(chatbot_router, prefix="/chatbot", tags=["Chatbot"])
api_router.include_router(feedback_router, prefix="/feedback", tags=["Feedback"])


@api_router.get("/health")
async def health_check():
    logger.info("health_check_called")
    return {"status": "healthy", "version": "1.0.0"}
