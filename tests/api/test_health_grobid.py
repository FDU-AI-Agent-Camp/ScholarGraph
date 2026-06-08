"""API tests: GET /health GROBID sidecar disclosure (Phase C / C9)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient
from tests.api.conftest import assert_success_envelope


@pytest.mark.asyncio
async def test_health_grobid_connected_when_sidecar_alive(api_client: AsyncClient) -> None:
    with patch("backend.api.routes.health.check_grobid_isalive", return_value=True):
        response = await api_client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert_success_envelope(body)
    assert body["data"]["grobid_connected"] is True
    assert "可达" in body["data"]["grobid_note"]


@pytest.mark.asyncio
async def test_health_grobid_disconnected_when_sidecar_down(api_client: AsyncClient) -> None:
    with patch("backend.api.routes.health.check_grobid_isalive", return_value=False):
        response = await api_client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert_success_envelope(body)
    assert body["data"]["grobid_connected"] is False
    assert "不可达" in body["data"]["grobid_note"]


@pytest.mark.asyncio
async def test_health_includes_configured_grobid_url(api_client: AsyncClient) -> None:
    with patch("backend.api.routes.health.check_grobid_isalive", return_value=False):
        response = await api_client.get("/api/v1/health")

    grobid_url = response.json()["data"]["grobid_url"]
    assert isinstance(grobid_url, str)
    assert grobid_url.startswith("http")
