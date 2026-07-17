# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""HTTP: GET /api/v1/papers/{id}/graph — success, 409 GRAPH_NOT_READY, 404."""

from __future__ import annotations

import pytest
from backend.graph.store import GraphStore
from httpx import AsyncClient
from tests.api.conftest import assert_error_envelope, assert_success_envelope

READY_PAPER_ID = "hss-001"
PROCESSING_PAPER_ID = "hss-002"
FAILED_PAPER_ID = "hss-failed-001"


@pytest.mark.asyncio
async def test_graph_ready_paper_returns_200_unified_graph(api_client: AsyncClient) -> None:
    response = await api_client.get(f"/api/v1/papers/{READY_PAPER_ID}/graph")
    assert response.status_code == 200
    body = response.json()
    assert_success_envelope(body)
    data = body["data"]
    assert data["paper_id"] == READY_PAPER_ID
    assert isinstance(data["nodes"], list)
    assert isinstance(data["edges"], list)
    assert len(data["nodes"]) >= 1


@pytest.mark.asyncio
async def test_graph_skeleton_view_returns_downsampled_graph(api_client: AsyncClient) -> None:
    response = await api_client.get(f"/api/v1/papers/{READY_PAPER_ID}/graph?view=skeleton")
    assert response.status_code == 200
    body = response.json()
    assert_success_envelope(body)
    data = body["data"]
    assert data["paper_id"] == READY_PAPER_ID
    assert isinstance(data["nodes"], list)
    assert isinstance(data["edges"], list)
    # hss-001 fixture has 3 nodes, so skeleton should keep all of them.
    assert len(data["nodes"]) >= 1


@pytest.mark.asyncio
async def test_graph_processing_paper_returns_409_graph_not_ready(api_client: AsyncClient) -> None:
    response = await api_client.get(f"/api/v1/papers/{PROCESSING_PAPER_ID}/graph")
    assert response.status_code == 409
    body = response.json()
    assert_error_envelope(body, code="GRAPH_NOT_READY")
    assert "轮询" in body["error"]["message"]


@pytest.mark.asyncio
async def test_graph_failed_paper_returns_409_graph_not_ready(api_client: AsyncClient) -> None:
    response = await api_client.get(f"/api/v1/papers/{FAILED_PAPER_ID}/graph")
    assert response.status_code == 409
    assert_error_envelope(response.json(), code="GRAPH_NOT_READY")


@pytest.mark.asyncio
async def test_graph_not_found_paper_returns_404(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/papers/does-not-exist/graph")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PAPER_NOT_FOUND"


@pytest.mark.asyncio
async def test_graph_ready_missing_graph_data_returns_409_with_message(api_client: AsyncClient) -> None:
    graph_path = GraphStore()._path(READY_PAPER_ID)
    backup = graph_path.read_text(encoding="utf-8") if graph_path.is_file() else None
    if graph_path.is_file():
        graph_path.unlink()

    response = await api_client.get(f"/api/v1/papers/{READY_PAPER_ID}/graph")
    assert response.status_code == 409
    body = response.json()
    assert_error_envelope(body, code="GRAPH_NOT_READY")
    assert "缺失" in body["error"]["message"]

    if backup is not None:
        graph_path.write_text(backup, encoding="utf-8")


@pytest.mark.asyncio
async def test_get_paper_not_found_returns_404(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/papers/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PAPER_NOT_FOUND"
    assert "does-not-exist" in response.json()["error"]["message"]
