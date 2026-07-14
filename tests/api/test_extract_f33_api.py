"""HTTP API: F.3 HSS graph node/edge contract on graph endpoints."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from backend.config import get_settings
from backend.graph.store import GraphStore
from backend.main import app
from backend.schemas.graph import HSS_EDGE_TYPES, HSS_NODE_TYPES, GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm
from httpx import ASGITransport, AsyncClient
from tests.api.conftest import assert_success_envelope
from tests.helpers.f33_hss_graphs import F33_FORBIDDEN_STEM_NODE_TYPES, assert_hss_excludes_stem_only_node_types
from tests.helpers.f33_stem_graphs import F33_FORBIDDEN_HSS_NODE_TYPES

pytestmark = pytest.mark.integration

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "docs" / "api" / "fixtures"
HSS_WHITELIST_NODE_VALUES = {node_type.value for node_type in HSS_NODE_TYPES}


@pytest.fixture
async def api_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def test_api_f33_graph_hss_fixture_passes_unified_schema() -> None:
    payload = json.loads((FIXTURES_DIR / "graph-hss.json").read_text(encoding="utf-8"))
    graph = UnifiedPaperGraph.model_validate(payload["data"])
    assert graph.paradigm.value == "HSS"
    assert {node.type for node in graph.nodes} <= HSS_WHITELIST_NODE_VALUES
    assert {edge.type for edge in graph.edges} <= HSS_EDGE_TYPES
    assert_hss_excludes_stem_only_node_types(graph)


@pytest.mark.asyncio
async def test_api_f33_get_hss_graph_returns_whitelisted_node_types(
    api_client: AsyncClient,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_isolated_hss_fixture_graph(tmp_path, monkeypatch)
    response = await api_client.get("/api/v1/papers/hss-001/graph")

    assert response.status_code == 200
    body = response.json()
    assert_success_envelope(body)
    data = body["data"]
    assert data["paper_id"] == "hss-001"
    assert data.get("paradigm") == "HSS" or any(
        node.get("type") in HSS_WHITELIST_NODE_VALUES for node in data.get("nodes", [])
    )

    node_types = {node["type"] for node in data["nodes"]}
    edge_types = {edge["type"] for edge in data["edges"]}
    assert node_types <= HSS_WHITELIST_NODE_VALUES
    assert edge_types <= HSS_EDGE_TYPES
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_api_f33_get_hss_graph_contains_argumentation_types(
    api_client: AsyncClient,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_isolated_hss_fixture_graph(tmp_path, monkeypatch)
    response = await api_client.get("/api/v1/papers/hss-001/graph")

    assert response.status_code == 200
    data = response.json()["data"]
    node_types = {node["type"] for node in data["nodes"]}
    edge_types = {edge["type"] for edge in data["edges"]}

    assert "Thesis" in node_types
    assert "SubArgument" in node_types
    assert "SUB_ARGUMENT_OF" in edge_types
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_api_f33_get_hss_graph_excludes_stem_only_node_types(
    api_client: AsyncClient,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_isolated_hss_fixture_graph(tmp_path, monkeypatch)
    response = await api_client.get("/api/v1/papers/hss-001/graph")

    assert response.status_code == 200
    node_types = {node["type"] for node in response.json()["data"]["nodes"]}
    forbidden = node_types & F33_FORBIDDEN_STEM_NODE_TYPES
    assert not forbidden, f"HSS API graph must not expose STEM-only types: {sorted(forbidden)}"
    for stem_type in ("Metric", "Baseline", "Dataset"):
        assert stem_type not in node_types
    get_settings.cache_clear()


def _seed_isolated_hss_fixture_graph(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    graphs_dir = tmp_path / "graphs"
    graphs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graphs_dir))
    get_settings.cache_clear()
    from backend.services.paper_service import get_paper_service

    get_paper_service.cache_clear()
    payload = json.loads((FIXTURES_DIR / "graph-hss.json").read_text(encoding="utf-8"))
    GraphStore(base_dir=graphs_dir).save(UnifiedPaperGraph.model_validate(payload["data"]))


@pytest.mark.asyncio
async def test_api_f33_get_stem_graph_does_not_expose_hss_only_types(
    api_client: AsyncClient,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graphs_dir = tmp_path / "graphs"
    graphs_dir.mkdir()
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graphs_dir))
    get_settings.cache_clear()

    GraphStore(base_dir=graphs_dir).save(
        UnifiedPaperGraph(
            paper_id="stem-001",
            paradigm=Paradigm.STEM,
            nodes=[
                GraphNode(id="n_method", label="Transformer 方法", type="Method"),
                GraphNode(id="n_claim", label="性能声称", type="Claim"),
            ],
            edges=[
                GraphEdge(
                    id="e1",
                    source="n_method",
                    target="n_claim",
                    label="SUPPORTS",
                    type="SUPPORTS",
                ),
            ],
        ),
    )

    response = await api_client.get("/api/v1/papers/stem-001/graph")

    assert response.status_code == 200
    data = response.json()["data"]
    node_types = {node["type"] for node in data["nodes"]}
    forbidden = node_types & F33_FORBIDDEN_HSS_NODE_TYPES
    assert not forbidden, f"STEM API graph must not expose HSS-only types: {sorted(forbidden)}"
    for hss_type in ("AnalyticalLens", "IntellectualContext", "ObjectOrData"):
        assert hss_type not in node_types

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_api_f33_get_stem_graph_contains_verification_chain_types(
    api_client: AsyncClient,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graphs_dir = tmp_path / "graphs"
    graphs_dir.mkdir()
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graphs_dir))
    get_settings.cache_clear()

    from tests.helpers.f33_stem_graphs import minimal_f33_stem_graph

    GraphStore(base_dir=graphs_dir).save(minimal_f33_stem_graph(paper_id="stem-001"))

    response = await api_client.get("/api/v1/papers/stem-001/graph")

    assert response.status_code == 200
    data = response.json()["data"]
    node_types = {node["type"] for node in data["nodes"]}
    edge_types = {edge["type"] for edge in data["edges"]}
    assert "ResearchQuestion" in node_types
    assert "Method" in node_types
    assert "ADDRESSES" in edge_types
    assert "SUPPORTS" in edge_types
    assert not (node_types & F33_FORBIDDEN_HSS_NODE_TYPES)

    get_settings.cache_clear()
