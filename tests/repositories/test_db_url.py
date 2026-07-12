"""Unit tests for async database URL conversion."""

from __future__ import annotations

from backend.db.url import to_async_database_url


def test_sqlite_sync_url_converts_to_aiosqlite() -> None:
    assert to_async_database_url("sqlite:///./data/test.db") == "sqlite+aiosqlite:///./data/test.db"


def test_sqlite_async_url_is_idempotent() -> None:
    url = "sqlite+aiosqlite:///./data/test.db"
    assert to_async_database_url(url) == url


def test_postgresql_url_converts_to_asyncpg() -> None:
    assert (
        to_async_database_url("postgresql://user:pass@localhost/scholargraph")
        == "postgresql+asyncpg://user:pass@localhost/scholargraph"
    )
