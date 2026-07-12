"""API pagination and validation boundary tests (BND-08~10)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

VALID_PDF = b"%PDF-1.4\n% api boundary test"


@pytest.mark.asyncio
async def test_list_papers_limit_100_accepted(
    api_client: AsyncClient,
    persistence_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("backend.services.paper_service.schedule_paper_pipeline", lambda *_a, **_k: None)
    response = await api_client.get("/api/v1/papers", params={"limit": 100})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_papers_limit_101_rejected(
    api_client: AsyncClient,
    persistence_env,
) -> None:
    response = await api_client.get("/api/v1/papers", params={"limit": 101})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_papers_negative_offset_rejected(
    api_client: AsyncClient,
    persistence_env,
) -> None:
    response = await api_client.get("/api/v1/papers", params={"offset": -1})
    assert response.status_code == 422
