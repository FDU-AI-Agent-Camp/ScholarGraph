# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Authorization / cross-resource access tests for persistence-backed paper APIs."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from tests.api.conftest import assert_error_envelope

VALID_PDF = b"%PDF-1.4\n% authz test"


@pytest.mark.asyncio
async def test_cannot_read_other_paper_status_without_knowledge_of_id(
    api_client: AsyncClient,
    persistence_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Enumerate random ids should not leak existence beyond 404 envelope."""
    monkeypatch.setattr("backend.services.paper_service.schedule_paper_pipeline", lambda *_a, **_k: None)
    create = await api_client.post(
        "/api/v1/papers",
        files={"file": ("owned.pdf", VALID_PDF, "application/pdf")},
    )
    owned_id = create.json()["data"]["paper_id"]

    foreign = await api_client.get("/api/v1/papers/not-owned-paper-id/status")
    assert foreign.status_code == 404
    assert_error_envelope(foreign.json(), code="PAPER_NOT_FOUND")
    assert foreign.json()["error"]["message"]

    owned = await api_client.get(f"/api/v1/papers/{owned_id}/status")
    assert owned.status_code == 200


@pytest.mark.asyncio
async def test_sql_injection_style_paper_id_returns_404_not_500(
    api_client: AsyncClient,
    persistence_env,
) -> None:
    response = await api_client.get("/api/v1/papers/' OR 1=1 --")
    assert response.status_code == 404
    assert_error_envelope(response.json(), code="PAPER_NOT_FOUND")


@pytest.mark.asyncio
async def test_percent_encoded_slash_blocked_at_router_level(
    api_client: AsyncClient,
    persistence_env,
) -> None:
    """``%2F`` inside a path segment is rejected before the papers handler runs."""
    response = await api_client.get("/api/v1/papers/foo%2Fbar")
    assert response.status_code == 404
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_graph_endpoint_denies_foreign_paper(
    api_client: AsyncClient,
    persistence_env,
) -> None:
    response = await api_client.get("/api/v1/papers/foreign-paper/graph")
    assert response.status_code == 404
    assert_error_envelope(response.json(), code="PAPER_NOT_FOUND")


@pytest.mark.asyncio
async def test_qa_stream_denies_foreign_paper(
    api_client: AsyncClient,
    persistence_env,
) -> None:
    response = await api_client.post(
        "/api/v1/papers/foreign-paper/qa/stream",
        json={"question": "这篇论文的核心论点是什么？"},
    )
    assert response.status_code == 404
    assert_error_envelope(response.json(), code="PAPER_NOT_FOUND")
