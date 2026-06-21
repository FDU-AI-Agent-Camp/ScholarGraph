"""Stress tests for LLM-return cleaning, truncation, and warning propagation."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from backend.agents.extract_edges import build_edges_with_llm
from backend.agents.extract_nodes import extract_nodes_with_llm
from backend.config import Settings, get_settings
from backend.graph.extract_workflow import build_extract_subgraph
from backend.llm.client import LlmClient, reset_llm_client_cache
from backend.schemas.extract_phase import ExtractedEdgeList, ExtractedNode, ExtractedNodeList
from backend.schemas.paradigm import Paradigm
from langchain_core.messages import AIMessage


@pytest.fixture
def live_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enable live-mode extraction path for stress tests (no real network call)."""
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("EXTRACT_TWO_PHASE_ENABLED", "true")
    monkeypatch.setenv("EXTRACT_HEURISTIC_FALLBACK", "true")
    get_settings.cache_clear()
    reset_llm_client_cache()


def _settings() -> Settings:
    settings = get_settings()
    settings.extract_max_input_chars = 20_000
    return settings


class _FakeChat:
    """Minimal fake chat that returns a fixed AIMessage."""

    def __init__(self, content: str) -> None:
        self._content = content

    async def ainvoke(self, messages: list[object]) -> AIMessage:
        return AIMessage(content=self._content)


def _fake_llm_client(raw_content: str) -> LlmClient:
    """Build an LlmClient whose primary chat always returns ``raw_content``."""
    client = LlmClient.__new__(LlmClient)
    client._chat = _FakeChat(raw_content)
    client._fallback_chat = None
    return client


def _dirty_node_json(*, label_length: int = 200, span_length: int = 700) -> str:
    """Return a node payload wrapped in markdown fences with extra text."""
    long_label = "A" * label_length
    long_span = "B" * span_length
    payload = {
        "paradigm": Paradigm.HSS.value,
        "warnings": [],
        "nodes": [
            {
                "id": "n1",
                "label": long_label,
                "type": "Thesis",
                "source_span": long_span,
            }
        ],
    }
    json_text = json.dumps(payload, ensure_ascii=False)
    return f"Here is the JSON you asked for:\n\n```json\n{json_text}\n```\n\nHope this helps!"


def _dirty_edge_json(*, label_length: int = 200, span_length: int = 700) -> str:
    """Return an edge payload wrapped in markdown fences with extra text."""
    long_label = "C" * label_length
    long_span = "D" * span_length
    payload = {
        "paradigm": Paradigm.HSS.value,
        "warnings": [],
        "node_ids": ["n1"],
        "edges": [
            {
                "id": "e1",
                "source": "n1",
                "target": "n1",
                "label": long_label,
                "type": "SUPPORTS",
                "source_span": long_span,
            }
        ],
    }
    json_text = json.dumps(payload, ensure_ascii=False)
    return f"Sure!\n```\n{json_text}\n```\nDone."


@pytest.mark.asyncio
async def test_extract_nodes_cleans_markdown_and_truncates_long_fields(live_env: None) -> None:
    """Dirty LLM node output is stripped, parsed, and truncated with warnings."""
    _ = live_env
    client = _fake_llm_client(_dirty_node_json())

    node_list = await extract_nodes_with_llm(
        "Title: Example\nWe argue that example works.",
        Paradigm.HSS,
        paper_id="paper-stress-001",
        title="Example",
        llm_client=client,
        settings=_settings(),
    )

    assert len(node_list.nodes) == 1
    node = node_list.nodes[0]
    assert node.label.endswith("...")
    assert len(node.label) == 120
    assert node.source_span.endswith("...")
    assert len(node.source_span) == 500
    assert "extract_field_truncated:node.label" in node_list.warnings
    assert "extract_field_truncated:node.source_span" in node_list.warnings


@pytest.mark.asyncio
async def test_extract_edges_cleans_markdown_and_truncates_long_fields(live_env: None) -> None:
    """Dirty LLM edge output is stripped, parsed, and truncated with warnings."""
    _ = live_env
    nodes = ExtractedNodeList(
        paradigm=Paradigm.HSS,
        nodes=[ExtractedNode(id="n1", label="Thesis", type="Thesis")],
    )
    client = _fake_llm_client(_dirty_edge_json())

    edge_list = await build_edges_with_llm(
        nodes,
        "Title: Example\nWe argue that example works.",
        paper_id="paper-stress-002",
        llm_client=client,
        settings=_settings(),
    )

    assert len(edge_list.edges) == 1
    edge = edge_list.edges[0]
    assert edge.label.endswith("...")
    assert len(edge.label) == 120
    assert edge.source_span.endswith("...")
    assert len(edge.source_span) == 500
    assert "extract_field_truncated:edge.label" in edge_list.warnings
    assert "extract_field_truncated:edge.source_span" in edge_list.warnings


@pytest.mark.asyncio
async def test_subgraph_propagates_truncation_warnings(live_env: None) -> None:
    """Warnings from node/edge truncation flow into final extract_warnings."""
    _ = live_env
    nodes = ExtractedNodeList.model_validate_json(
        json.dumps(
            {
                "paradigm": Paradigm.HSS.value,
                "warnings": [],
                "nodes": [
                    {
                        "id": "n1",
                        "label": "A" * 200,
                        "type": "Thesis",
                        "source_span": "B" * 700,
                    }
                ],
            }
        ),
        context={"warnings": []},
    )
    edges = ExtractedEdgeList.model_validate_json(
        json.dumps(
            {
                "paradigm": Paradigm.HSS.value,
                "warnings": [],
                "node_ids": ["n1"],
                "edges": [
                    {
                        "id": "e1",
                        "source": "n1",
                        "target": "n1",
                        "label": "C" * 200,
                        "type": "SUPPORTS",
                        "source_span": "D" * 700,
                    }
                ],
            }
        ),
        context={"warnings": []},
    )

    assert "extract_field_truncated:node.label" in nodes.warnings
    assert "extract_field_truncated:edge.label" in edges.warnings

    with (
        patch("backend.agents.extract_nodes.extract_nodes_with_llm", new=AsyncMock(return_value=nodes)),
        patch("backend.agents.extract_edges.build_edges_with_llm", new=AsyncMock(return_value=edges)),
    ):
        subgraph = build_extract_subgraph().compile()
        final = await subgraph.ainvoke(
            {
                "paper_id": "paper-stress-003",
                "full_text": "Title: Example",
                "paradigm": Paradigm.HSS.value,
                "repair_attempts": 0,
                "extract_warnings": [],
            }
        )

    assert final.get("failed") is not True
    graph_data = final.get("graph")
    assert graph_data is not None
    # Labels/spans were truncated before becoming GraphNode/GraphEdge.
    assert graph_data["nodes"][0]["label"].endswith("...")
    assert len(graph_data["nodes"][0]["label"]) == 120

    extract_warnings = final.get("extract_warnings", [])
    assert "extract_field_truncated:node.label" in extract_warnings
    assert "extract_field_truncated:node.source_span" in extract_warnings
    assert "extract_field_truncated:edge.label" in extract_warnings
    assert "extract_field_truncated:edge.source_span" in extract_warnings
