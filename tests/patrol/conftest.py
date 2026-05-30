"""Shared fixtures for patrol API and integration tests."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from backend.config import get_settings
from backend.main import app
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
def _disable_patrol_llm_unless_llm_tests(monkeypatch, request) -> None:
    """Avoid real LLM calls in patrol tests (fallback templates); test_llm_summary opts out."""
    if request.module.__name__.endswith(("test_llm_summary", "test_patrol_llm_integration")):
        return

    async def _no_llm(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr("backend.patrol.llm_summary.generate_patrol_summary", _no_llm)
    monkeypatch.setattr("backend.patrol.lens_clash.generate_patrol_summary", _no_llm)
    monkeypatch.setattr("backend.patrol.contradiction.generate_patrol_summary", _no_llm)


@pytest.fixture
def patrol_graph_dir(tmp_path, monkeypatch):
    """Isolated GRAPH_DATA_DIR with cleared settings cache."""
    graph_dir = tmp_path / "graphs"
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_dir))
    get_settings.cache_clear()
    yield graph_dir
    get_settings.cache_clear()


@pytest.fixture
async def api_client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def assert_api_envelope(body: dict) -> None:
    assert "data" in body
    assert "meta" in body
    assert isinstance(body["meta"].get("request_id"), str)
    assert body["meta"]["request_id"]
