"""Convert sync DATABASE_URL values to SQLAlchemy async driver URLs."""

from __future__ import annotations

SQLITE_ASYNC_PREFIX = "sqlite+aiosqlite:///"


def to_async_database_url(database_url: str) -> str:
    """Map ``sqlite:///`` and other sync URLs to their async equivalents."""
    if database_url.startswith("sqlite+aiosqlite:"):
        return database_url
    if database_url.startswith("sqlite:///"):
        return database_url.replace("sqlite:///", SQLITE_ASYNC_PREFIX, 1)
    if database_url.startswith("postgresql+asyncpg:"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return database_url
