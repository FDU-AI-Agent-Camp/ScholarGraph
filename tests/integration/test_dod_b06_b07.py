# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""V1 DoD B-06 / B-07 — GET graph UnifiedPaperGraph + G6 conversion separation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from backend.graph.store import GraphStore
from backend.graph.workflow import run_paper_pipeline
from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.paper import PaperStatus
from backend.services.paper_service import get_paper_service
from httpx import AsyncClient

from tests.api.conftest import assert_error_envelope, assert_success_envelope
from tests.conftest import mock_pipeline_node_services

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "docs" / "api" / "fixtures"
ROUTES_PAPERS = Path(__file__).resolve().parents[2] / "backend" / "api" / "routes" / "papers.py"
READY_PAPER_ID = "hss-001"
PROCESSING_PAPER_ID = "hss-002"
FAILED_PAPER_ID = "hss-failed-001"

pytestmark = pytest.mark.usefixtures("graph_hss_fixture_env")


def _load_graph_hss_fixture() -> dict:
    return json.loads((FIXTURES_DIR / "graph-hss.json").read_text(encoding="utf-8"))["data"]


def _assert_unified_graph_shape(data: dict) -> None:
    """B-06: flat GraphNode/GraphEdge — not G6 ``{id, data:{label}}`` nesting."""
    assert "paper_id" in data
    assert "paradigm" in data
    assert isinstance(data["nodes"], list)
    assert isinstance(data["edges"], list)
    if data["nodes"]:
        node = data["nodes"][0]
        assert "label" in node
        assert "type" in node
        assert "data" not in node or isinstance(node.get("data"), dict)
        assert "id" in node
        # G6 adapter nests label under data; API must not.
        assert not isinstance(node.get("data"), dict) or "label" not in node.get("data", {})


@pytest.mark.asyncio
async def test_b06_get_graph_returns_unified_paper_graph_from_graph_store(api_client: AsyncClient) -> None:
    response = await api_client.get(f"/api/v1/papers/{READY_PAPER_ID}/graph")
    assert response.status_code == 200
    body = response.json()
    assert_success_envelope(body)
    data = body["data"]
    _assert_unified_graph_shape(data)

    expected = _load_graph_hss_fixture()
    assert data["paper_id"] == READY_PAPER_ID
    assert data["paradigm"] == expected["paradigm"]
    assert len(data["nodes"]) == len(expected["nodes"])
    assert data["nodes"][0]["id"] == expected["nodes"][0]["id"]
    assert data["nodes"][0]["label"] == expected["nodes"][0]["label"]


@pytest.mark.asyncio
async def test_b06_graph_store_round_trip_matches_fixture(api_client: AsyncClient) -> None:
    """Seeded fixture is persisted to GraphStore and loaded by get_graph()."""
    loaded = GraphStore().load(READY_PAPER_ID)
    assert loaded is not None
    assert loaded.paper_id == READY_PAPER_ID

    response = await api_client.get(f"/api/v1/papers/{READY_PAPER_ID}/graph")
    api_graph = response.json()["data"]
    assert api_graph["nodes"][0]["label"] == loaded.nodes[0].label


@pytest.mark.asyncio
async def test_b06_processing_paper_returns_409_graph_not_ready(api_client: AsyncClient) -> None:
    response = await api_client.get(f"/api/v1/papers/{PROCESSING_PAPER_ID}/graph")
    assert response.status_code == 409
    assert_error_envelope(response.json(), code="GRAPH_NOT_READY")


@pytest.mark.asyncio
async def test_b06_ready_paper_missing_graph_file_returns_409(api_client: AsyncClient) -> None:
    graph_path = GraphStore().graph_path_for(READY_PAPER_ID)
    backup = graph_path.read_text(encoding="utf-8") if graph_path.is_file() else None
    if graph_path.is_file():
        graph_path.unlink()

    try:
        response = await api_client.get(f"/api/v1/papers/{READY_PAPER_ID}/graph")
        assert response.status_code == 409
        assert_error_envelope(response.json(), code="GRAPH_NOT_READY")
        assert "缺失" in response.json()["error"]["message"]
    finally:
        if backup is not None:
            graph_path.write_text(backup, encoding="utf-8")


@pytest.mark.asyncio
async def test_b07_route_does_not_emit_g6_nested_nodes(api_client: AsyncClient) -> None:
    response = await api_client.get(f"/api/v1/papers/{READY_PAPER_ID}/graph")
    data = response.json()["data"]
    g6_shape = GraphStore.to_g6(UnifiedPaperGraph.model_validate(data))
    assert g6_shape["nodes"][0]["data"]["label"] == data["nodes"][0]["label"]
    assert "label" not in data["nodes"][0].get("data", {})


def test_b07_to_g6_is_separate_from_http_contract() -> None:
    """BE to_g6() produces G6 v5 nesting; UnifiedPaperGraph remains flat."""
    hss_graph = UnifiedPaperGraph.model_validate(_load_graph_hss_fixture())
    g6 = GraphStore.to_g6(hss_graph)
    assert g6["nodes"][0]["data"]["label"] == hss_graph.nodes[0].label
    dumped = hss_graph.model_dump()
    assert dumped["nodes"][0]["label"] == hss_graph.nodes[0].label
    assert "label" not in dumped["nodes"][0].get("data", {})


def test_b07_papers_route_does_not_call_to_g6() -> None:
    """HTTP layer returns UnifiedPaperGraph; G6 conversion stays in GraphStore.to_g6 (tests/tools)."""
    route_src = ROUTES_PAPERS.read_text(encoding="utf-8")
    assert "to_g6" not in route_src
    assert "get_graph" in route_src


@pytest.mark.asyncio
async def test_b06_full_fixture_node_and_edge_shape(api_client: AsyncClient) -> None:
    """Functional: all graph-hss nodes/edges round-trip with flat GraphNode/GraphEdge fields."""
    expected = _load_graph_hss_fixture()
    response = await api_client.get(f"/api/v1/papers/{READY_PAPER_ID}/graph")
    assert response.status_code == 200
    data = response.json()["data"]

    expected_ids = {node["id"] for node in expected["nodes"]}
    assert {node["id"] for node in data["nodes"]} == expected_ids
    assert data["edges"][0]["type"] == expected["edges"][0]["type"]
    assert data["edges"][0]["source"] == expected["edges"][0]["source"]


@pytest.mark.asyncio
async def test_b06_unknown_paper_returns_404_json_envelope(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/papers/ghost-paper/graph")
    assert response.status_code == 404
    assert "application/json" in response.headers.get("content-type", "")
    assert_error_envelope(response.json(), code="PAPER_NOT_FOUND")


@pytest.mark.asyncio
async def test_b06_failed_paper_returns_409_graph_not_ready(api_client: AsyncClient) -> None:
    response = await api_client.get(f"/api/v1/papers/{FAILED_PAPER_ID}/graph")
    assert response.status_code == 409
    body = response.json()
    assert_error_envelope(body, code="GRAPH_NOT_READY")
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]


@pytest.mark.asyncio
async def test_b06_success_response_includes_meta_request_id(api_client: AsyncClient) -> None:
    response = await api_client.get(f"/api/v1/papers/{READY_PAPER_ID}/graph")
    body = response.json()
    assert_success_envelope(body)
    assert isinstance(body["meta"].get("request_id"), str)
    assert body["meta"]["request_id"]


@pytest.mark.asyncio
async def test_b06_pipeline_complete_then_http_graph_unified(
    api_client: AsyncClient,
    integration_paper: tuple[str, Path],
) -> None:
    """Functional chain: pipeline ready → GraphStore → GET graph returns UnifiedPaperGraph."""
    paper_id, pdf_path = integration_paper

    with mock_pipeline_node_services(paper_id):
        final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("failed") is not True
    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.READY

    response = await api_client.get(f"/api/v1/papers/{paper_id}/graph")
    assert response.status_code == 200
    data = response.json()["data"]
    _assert_unified_graph_shape(data)
    assert data["paper_id"] == paper_id
    assert len(data["nodes"]) >= 1


@pytest.mark.asyncio
async def test_b06_isolated_graph_dir_does_not_auto_seed_fixture_graph(
    api_client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Boundary: non-default GRAPH_DATA_DIR stays empty; ready paper → 409 图谱数据缺失."""
    from backend.config import get_settings
    from backend.services.paper_service import get_paper_service

    isolated = tmp_path / "isolated-graphs"
    isolated.mkdir()
    monkeypatch.setenv("GRAPH_DATA_DIR", str(isolated))
    get_settings.cache_clear()
    get_paper_service.cache_clear()

    response = await api_client.get(f"/api/v1/papers/{READY_PAPER_ID}/graph")
    assert response.status_code == 409
    assert_error_envelope(response.json(), code="GRAPH_NOT_READY")
    assert "缺失" in response.json()["error"]["message"]
