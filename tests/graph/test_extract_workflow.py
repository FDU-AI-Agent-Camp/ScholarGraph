"""Tests for the two-phase extraction sub-graph (backend.graph.extract_workflow)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE
from backend.config import get_settings
from backend.graph.extract_workflow import build_extract_subgraph
from backend.llm.client import reset_llm_client_cache
from backend.schemas.extract_phase import ExtractedEdge, ExtractedEdgeList, ExtractedNode, ExtractedNodeList
from backend.schemas.paradigm import Paradigm


@pytest.fixture
def two_phase_live_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enable the two-phase extraction live path for these tests."""
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("EXTRACT_TWO_PHASE_ENABLED", "true")
    monkeypatch.setenv("EXTRACT_HEURISTIC_FALLBACK", "true")
    monkeypatch.setenv("EXTRACT_REPAIR_MAX_RETRIES", "2")
    get_settings.cache_clear()
    reset_llm_client_cache()


def _hss_nodes() -> ExtractedNodeList:
    return ExtractedNodeList(
        paradigm=Paradigm.HSS,
        nodes=[ExtractedNode(id="n1", label="Thesis", type="Thesis")],
    )


def _hss_edges() -> ExtractedEdgeList:
    return ExtractedEdgeList(
        paradigm=Paradigm.HSS,
        edges=[ExtractedEdge(id="e1", source="n1", target="n1", label="supports", type="SUPPORTS")],
        node_ids=["n1"],
    )


def _invalid_hss_nodes() -> ExtractedNodeList:
    """Return an HSS node list with a forbidden node type (passes init, invalid value)."""
    node_list = ExtractedNodeList(
        paradigm=Paradigm.HSS,
        nodes=[ExtractedNode(id="n1", label="Bad", type="Thesis")],
    )
    node_list.nodes[0].type = "Method"
    return node_list


def _invalid_hss_edges() -> ExtractedEdgeList:
    """Return an HSS edge list with a dangling target (passes init, invalid reference)."""
    edge_list = ExtractedEdgeList(
        paradigm=Paradigm.HSS,
        edges=[ExtractedEdge(id="e1", source="n1", target="n1", label="supports", type="SUPPORTS")],
        node_ids=["n1"],
    )
    edge_list.edges[0].target = "n2"
    return edge_list


@pytest.mark.asyncio
async def test_subgraph_success_returns_valid_graph(two_phase_live_env: None) -> None:
    """Both phases succeed and the sub-graph returns a UnifiedPaperGraph."""
    _ = two_phase_live_env
    nodes = _hss_nodes()
    edges = _hss_edges()

    with (
        patch("backend.agents.extract_nodes.extract_nodes_with_llm", new=AsyncMock(return_value=nodes)),
        patch("backend.agents.extract_edges.build_edges_with_llm", new=AsyncMock(return_value=edges)),
    ):
        subgraph = build_extract_subgraph().compile()
        final = await subgraph.ainvoke(
            {
                "paper_id": "paper-001",
                "full_text": "Title: Example\nWe argue that example works.",
                "paradigm": Paradigm.HSS.value,
                "repair_attempts": 0,
                "extract_warnings": [],
            }
        )

    assert final.get("failed") is not True
    graph_data = final.get("graph")
    assert graph_data is not None
    assert graph_data["paper_id"] == "paper-001"
    assert graph_data["paradigm"] == Paradigm.HSS.value
    assert len(graph_data["nodes"]) == 1
    assert len(graph_data["edges"]) == 1
    assert final.get("extract_warnings") == []


@pytest.mark.asyncio
async def test_subgraph_retries_nodes_on_validation_failure(two_phase_live_env: None) -> None:
    """A forbidden node type triggers a retry of the node-extraction step."""
    _ = two_phase_live_env
    good_nodes = _hss_nodes()
    bad_nodes = _invalid_hss_nodes()
    edges = _hss_edges()

    node_mock = AsyncMock(side_effect=[bad_nodes, good_nodes])
    edge_mock = AsyncMock(return_value=edges)

    with (
        patch("backend.agents.extract_nodes.extract_nodes_with_llm", new=node_mock),
        patch("backend.agents.extract_edges.build_edges_with_llm", new=edge_mock),
    ):
        subgraph = build_extract_subgraph().compile()
        final = await subgraph.ainvoke(
            {
                "paper_id": "paper-002",
                "full_text": "Title: Example",
                "paradigm": Paradigm.HSS.value,
                "repair_attempts": 0,
                "extract_warnings": [],
            }
        )

    assert final.get("failed") is not True
    assert final.get("graph") is not None
    assert node_mock.await_count == 2
    # ``build_edges`` runs before combined validation detects the node error,
    # so it is invoked once per iteration as well.
    assert edge_mock.await_count == 2


@pytest.mark.asyncio
async def test_subgraph_retries_edges_on_validation_failure(two_phase_live_env: None) -> None:
    """A dangling edge triggers a retry of the edge-building step."""
    _ = two_phase_live_env
    nodes = _hss_nodes()
    good_edges = _hss_edges()
    bad_edges = _invalid_hss_edges()

    node_mock = AsyncMock(return_value=nodes)
    edge_mock = AsyncMock(side_effect=[bad_edges, good_edges])

    with (
        patch("backend.agents.extract_nodes.extract_nodes_with_llm", new=node_mock),
        patch("backend.agents.extract_edges.build_edges_with_llm", new=edge_mock),
    ):
        subgraph = build_extract_subgraph().compile()
        final = await subgraph.ainvoke(
            {
                "paper_id": "paper-003",
                "full_text": "Title: Example",
                "paradigm": Paradigm.HSS.value,
                "repair_attempts": 0,
                "extract_warnings": [],
            }
        )

    assert final.get("failed") is not True
    assert final.get("graph") is not None
    # Depending on LangGraph scheduling, ``extract_nodes`` may be replayed once
    # when the edge step is retried; the important behavior is single edge retry.
    assert node_mock.await_count >= 1
    assert edge_mock.await_count == 2


@pytest.mark.asyncio
async def test_subgraph_falls_back_when_retries_exhausted(two_phase_live_env: None) -> None:
    """After max retries the sub-graph returns a heuristic graph with a warning."""
    _ = two_phase_live_env
    bad_nodes = _invalid_hss_nodes()
    edges = _hss_edges()

    node_mock = AsyncMock(return_value=bad_nodes)
    edge_mock = AsyncMock(return_value=edges)

    with (
        patch("backend.agents.extract_nodes.extract_nodes_with_llm", new=node_mock),
        patch("backend.agents.extract_edges.build_edges_with_llm", new=edge_mock),
    ):
        subgraph = build_extract_subgraph().compile()
        final = await subgraph.ainvoke(
            {
                "paper_id": "paper-004",
                "full_text": "Title: Example\nWe argue that example works.",
                "paradigm": Paradigm.HSS.value,
                "repair_attempts": 0,
                "extract_warnings": [],
            }
        )

    assert final.get("failed") is not True
    assert final.get("graph") is not None
    assert EXTRACT_HEURISTIC_FALLBACK_CODE in final.get("extract_warnings", [])
    # Initial attempt + 2 retries = 3 node calls; edges are built each iteration.
    assert node_mock.await_count == 3
    assert edge_mock.await_count == 3


@pytest.mark.asyncio
async def test_subgraph_propagates_service_error(two_phase_live_env: None) -> None:
    """An unrecoverable LLM failure is surfaced as a sub-graph failure patch."""
    _ = two_phase_live_env
    from backend.services.errors import ServiceError

    node_mock = AsyncMock(side_effect=ServiceError("PIPELINE_FAILED", "LLM unreachable"))

    with patch("backend.agents.extract_nodes.extract_nodes_with_llm", new=node_mock):
        subgraph = build_extract_subgraph().compile()
        final = await subgraph.ainvoke(
            {
                "paper_id": "paper-005",
                "full_text": "Title: Example",
                "paradigm": Paradigm.HSS.value,
                "repair_attempts": 0,
                "extract_warnings": [],
            }
        )

    assert final.get("failed") is True
    assert final.get("error_code") == "PIPELINE_FAILED"
    assert "LLM unreachable" in final.get("error_message", "")
