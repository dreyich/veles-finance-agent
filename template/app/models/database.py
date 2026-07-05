"""Database models and engine for the application."""

from urllib.parse import quote_plus

from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.models.thread import Thread

# Async engine used by conversation_logger and other async DB writers.
# Uses psycopg v3 async driver (already in dependencies as psycopg[binary]).
_url = (
    f"postgresql+psycopg://"
    f"{quote_plus(settings.POSTGRES_USER)}:{quote_plus(settings.POSTGRES_PASSWORD)}"
    f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
)
async_engine = create_async_engine(_url, pool_size=5, max_overflow=10)

__all__ = ["Thread", "async_engine"]
