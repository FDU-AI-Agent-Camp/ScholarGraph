"""API tests: GET /health Patrol claim_evolution funnel disclosure."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient
from tests.api.conftest import assert_success_envelope


@pytest.mark.asyncio
async def test_health_patrol_funnel_disabled_in_live_mode(
    api_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("RERANKER_ENABLED", "false")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    from backend.config import get_settings

    get_settings.cache_clear()

    with patch("backend.api.routes.health.check_grobid_isalive", return_value=False):
        response = await api_client.get("/api/v1/health")

    get_settings.cache_clear()

    body = response.json()
    assert_success_envelope(body)
    data = body["data"]
    assert data["status"] == "degraded"
    assert data["components"]["patrol_service"]["claim_rq_funnel_enabled"] is False
    assert data["components"]["patrol_service"]["reranker_status"] == "DISABLED_FALLBACK_ACTIVE"
    assert data["components"]["patrol_service"]["status"] == "degraded"
    assert data["patrol_claim_rq_funnel_enabled"] is False
    assert isinstance(data["patrol_config_warnings"], list)
    assert len(data["patrol_config_warnings"]) >= 1
    assert "RERANKER_ENABLED=false" in data["patrol_config_warnings"][0]
    assert data["components"]["patrol_service"]["warnings"]
    assert any("Reranker is disabled" in item for item in data["components"]["patrol_service"]["warnings"])
    assert "严格双塔回退" in data["patrol_note"]


@pytest.mark.asyncio
async def test_health_patrol_funnel_enabled_when_reranker_configured(
    api_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("RERANKER_ENABLED", "true")
    monkeypatch.setenv("RERANKER_MODEL", "bge-reranker-v2-m3")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    from backend.config import get_settings

    get_settings.cache_clear()

    with patch("backend.api.routes.health.check_grobid_isalive", return_value=False):
        response = await api_client.get("/api/v1/health")

    get_settings.cache_clear()

    data = response.json()["data"]
    assert data["status"] == "healthy"
    assert data["components"]["patrol_service"]["claim_rq_funnel_enabled"] is True
    assert data["components"]["patrol_service"]["reranker_status"] == "READY"
    assert data["patrol_claim_rq_funnel_enabled"] is True
    assert data["patrol_config_warnings"] == []
    assert "漏斗已启用" in data["patrol_note"]
