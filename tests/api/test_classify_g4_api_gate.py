"""G.4 API gate: health exposes LLM_MODE; mock CI must not require live keys."""

from __future__ import annotations

import pytest
from backend.main import app
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration


@pytest.fixture
async def api_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_g4_health_reports_mock_llm_mode(api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "mock")
    from backend.config import get_settings

    get_settings.cache_clear()

    response = await api_client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["data"]["llm_mode"] == "mock"


@pytest.mark.asyncio
async def test_g4_health_mock_mode_without_api_key(api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.delenv("SCHOLARGRAPH_API_KEY", raising=False)
    from backend.config import get_settings
    from backend.llm.client import reset_llm_client_cache

    get_settings.cache_clear()
    reset_llm_client_cache()

    response = await api_client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["llm_mode"] == "mock"
    assert body["status"] == "healthy"
