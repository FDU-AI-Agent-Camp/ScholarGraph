"""Shared fixtures for HTTP API route tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from backend.config import get_settings
from backend.main import app
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def api_client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def upload_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated upload directory for POST /papers tests."""
    from backend.services.paper_service import get_paper_service

    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    get_settings.cache_clear()
    get_paper_service.cache_clear()
    yield tmp_path
    get_settings.cache_clear()
    get_paper_service.cache_clear()


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
