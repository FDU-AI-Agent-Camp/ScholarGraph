"""Tests for backend.agents.extract_chunked coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from backend.agents.extract_chunked import extract_chunked
from backend.config import get_settings
from backend.llm.client import reset_llm_client_cache
from backend.schemas.extract_phase import ExtractedEdge, ExtractedEdgeList, ExtractedNode, ExtractedNodeList
from backend.schemas.paradigm import Paradigm


@pytest.fixture
def live_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enable live-mode extraction path for chunked tests (no real network call)."""
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("EXTRACT_TWO_PHASE_ENABLED", "true")
    monkeypatch.setenv("EXTRACT_CHUNKED_ENABLED", "true")
    monkeypatch.setenv("EXTRACT_CHUNK_CONCURRENCY", "2")
    get_settings.cache_clear()
    reset_llm_client_cache()


@pytest.mark.asyncio
async def test_extract_chunked_routes_through_chunks(live_env: None) -> None:
    """Long text is split, nodes/edges extracted per chunk, and results merged."""
    _ = live_env

    intro = "Introduction\n\n" + "We introduce the problem. " * 200
    methods = "Methods\n\n" + "We use method X. " * 200
    text = intro + "\n\n" + methods

    node_call_idx = 0
    edge_call_idx = 0

    async def fake_nodes(*args: object, **kwargs: object) -> ExtractedNodeList:
        nonlocal node_call_idx
        labels_types = [
            ("Problem", "ResearchQuestion"),
            ("Method X", "Method"),
        ]
        label, node_type = labels_types[node_call_idx % len(labels_types)]
        node_call_idx += 1
        return ExtractedNodeList(
            paradigm=Paradigm.STEM,
            nodes=[ExtractedNode(id="n1", label=label, type=node_type)],
        )

    async def fake_edges(*args: object, **kwargs: object) -> ExtractedEdgeList:
        nonlocal edge_call_idx
        edge_call_idx += 1
        if edge_call_idx == 2:
            return ExtractedEdgeList(
                paradigm=Paradigm.STEM,
                edges=[
                    ExtractedEdge(
                        id="e1",
                        source="c1_n1",
                        target="c0_n1",
                        label="ADDRESSES",
                        type="ADDRESSES",
                    )
                ],
            )
        return ExtractedEdgeList(paradigm=Paradigm.STEM, edges=[])

    node_mock = AsyncMock(side_effect=fake_nodes)
    edge_mock = AsyncMock(side_effect=fake_edges)

    settings = get_settings()
    settings.extract_max_input_chars = len(text) - 1  # Force chunked path.
    settings.extract_chunk_max_chars = 5_000

    with (
        patch("backend.agents.extract_chunked.extract_nodes_with_llm", new=node_mock),
        patch("backend.agents.extract_chunked.build_edges_with_llm", new=edge_mock),
    ):
        result = await extract_chunked(text, Paradigm.STEM, paper_id="paper-chunk-001", settings=settings)

    assert node_mock.await_count >= 2
    assert edge_mock.await_count >= 2

    # First node call should include the body of the first chunk.
    first_call_text = node_mock.await_args_list[0].kwargs.get("full_text") or node_mock.await_args_list[0].args[0]
    assert "We introduce the problem" in first_call_text

    # Edge extraction should receive the global merged node directory.
    edge_call = edge_mock.await_args_list[1]
    edge_nodes = edge_call.kwargs.get("nodes") or edge_call.args[0]
    assert edge_nodes is not None
    assert len(edge_nodes.nodes) >= 2

    # Result should contain both merged nodes and the cross-chunk edge.
    node_labels = {n.label for n in result.nodes}
    assert "Problem" in node_labels
    assert "Method X" in node_labels
    assert len(result.edges) == 1
    assert result.edges[0].type == "ADDRESSES"
