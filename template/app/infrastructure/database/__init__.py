"""Infrastructure — PostgreSQL database access.

Re-exports from app.services.database (Strangler Fig adapter).
New code: from app.infrastructure.database import DatabaseService
"""
from app.services.database import DatabaseService

__all__ = ["DatabaseService"]
