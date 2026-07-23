# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Shared fixtures for HTTP API route tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from backend.config import get_settings
from backend.main import app
from httpx import ASGITransport, AsyncClient
from tests.helpers.persistence_testkit import init_isolated_database, reset_persistence_singletons


@pytest.fixture
async def api_client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def upload_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated upload directory and SQLite DB for POST /papers tests."""
    db_path = tmp_path / "scholargraph.db"
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("SEED_DEMO_PAPERS", "false")
    reset_persistence_singletons()
    asyncio.run(init_isolated_database(db_path))
    get_settings.cache_clear()
    from backend.services.paper_service import get_paper_service

    get_paper_service.cache_clear()
    yield tmp_path
    reset_persistence_singletons()
    get_settings.cache_clear()
    get_paper_service.cache_clear()


@pytest.fixture
def noop_event_bus_publish_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip RAG EventBus side effects; still promote INDEXING → terminal READY (P10).

    HTTP contract tests intentionally avoid Chroma/embedding work, but after the
    indexing gate papers must not remain stuck in ``indexing`` when the bus is cut.
    """

    async def _publish(_self: object, event: object) -> None:
        from backend.events.types import PipelineFinalized
        from backend.services.paper_pipeline_ops import get_paper_pipeline_ops_service

        if not isinstance(event, PipelineFinalized):
            return
        await get_paper_pipeline_ops_service().promote_paper_to_terminal_status(
            event.paper_id,
            success=True,
            preferred_terminal=event.terminal_status,
            warning_message=event.warning_message,
            publish_rag_indexed=False,
        )

    monkeypatch.setattr("backend.events.bus.EventBus.publish", _publish)


@pytest.fixture
def mock_upload_pipeline_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    noop_event_bus_publish_sync: None,
) -> tuple[Path, Path]:
    """Isolated upload + graph dirs, SQLite DB, and LLM_MODE=mock for upload→pipeline HTTP tests."""
    upload_path = tmp_path / "uploads"
    graph_path = tmp_path / "graphs"
    db_path = tmp_path / "scholargraph.db"
    upload_path.mkdir(parents=True, exist_ok=True)
    graph_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("UPLOAD_DIR", str(upload_path))
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("SEED_DEMO_PAPERS", "false")
    monkeypatch.setenv("LLM_MODE", "mock")
    reset_persistence_singletons()
    asyncio.run(init_isolated_database(db_path))
    yield upload_path, graph_path
    reset_persistence_singletons()


def assert_success_envelope(body: dict) -> None:
    assert "data" in body
    assert "meta" in body
    assert isinstance(body["meta"].get("request_id"), str)
    assert body["meta"]["request_id"]


def assert_error_envelope(body: dict, *, code: str) -> None:
    assert "error" in body
    assert body["error"]["code"] == code
    assert isinstance(body["error"].get("message"), str)
    assert body["error"]["message"]
