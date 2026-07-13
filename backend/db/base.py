"""Async SQLAlchemy engine and session factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from backend.config import get_settings
from backend.db.url import to_async_database_url

SQLITE_BUSY_TIMEOUT_SECONDS = 30


class Base(DeclarativeBase):
    """Declarative base for ScholarGraph ORM models."""


def _configure_sqlite_connection(dbapi_connection: object, _connection_record: object) -> None:
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@lru_cache
def get_async_engine() -> AsyncEngine:
    """Return a process-wide async engine bound to ``Settings.database_url``."""
    settings = get_settings()
    async_url = to_async_database_url(settings.database_url)
    connect_args: dict[str, object] = {}
    if async_url.startswith("sqlite+aiosqlite:"):
        connect_args = {
            "timeout": SQLITE_BUSY_TIMEOUT_SECONDS,
            "check_same_thread": False,
        }
    engine = create_async_engine(
        async_url,
        future=True,
        connect_args=connect_args,
    )
    if async_url.startswith("sqlite+aiosqlite:"):
        event.listens_for(engine.sync_engine, "connect")(_configure_sqlite_connection)
    return engine


@lru_cache
def get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        get_async_engine(),
        expire_on_commit=False,
        class_=AsyncSession,
    )


# Backward-compatible alias for repository code and Alembic env.
async_session_factory = get_async_session_factory


def reset_database_caches() -> None:
    """Clear cached engine/session factories (tests and env changes)."""
    from backend.repositories.async_bridge import dispose_cached_engine_if_present

    dispose_cached_engine_if_present()
    get_async_engine.cache_clear()
    get_async_session_factory.cache_clear()


@asynccontextmanager
async def get_async_session() -> AsyncIterator[AsyncSession]:
    """Open a short-lived session for one repository operation."""
    factory = get_async_session_factory()
    async with factory() as session:
        yield session
