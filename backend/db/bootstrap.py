"""Database schema initialization helpers."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine

from backend.db.base import Base


async def ensure_schema(engine: AsyncEngine) -> None:
    """Create tables when they do not exist (tests and first boot)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
