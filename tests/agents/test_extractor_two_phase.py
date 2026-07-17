# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Tests for the two-phase extraction routing in backend.agents.extractor."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE
from backend.agents.extractor import extract
from backend.config import get_settings
from backend.llm.client import reset_llm_client_cache
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm
from backend.services.errors import PIPELINE_FAILED_CODE, ServiceError


@pytest.fixture
def two_phase_live_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enable live mode + two-phase extraction for these tests."""
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("EXTRACT_TWO_PHASE_ENABLED", "true")
    monkeypatch.setenv("EXTRACT_HEURISTIC_FALLBACK", "true")
    get_settings.cache_clear()
    reset_llm_client_cache()


def _sample_graph(paper_id: str = "paper-001") -> UnifiedPaperGraph:
    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="Thesis", type="Thesis")],
        edges=[GraphEdge(id="e1", source="n1", target="n1", label="REF", type="REF")],
    )


@pytest.mark.asyncio
async def test_extract_routes_to_two_phase_subgraph(two_phase_live_env: None) -> None:
    """When two-phase is enabled, extract() calls the sub-graph and returns its result."""
    _ = two_phase_live_env
    expected_graph = _sample_graph("paper-001")

    with patch(
        "backend.graph.extract_workflow.run_extract_subgraph",
        new=AsyncMock(return_value=AsyncMock(graph=expected_graph, warnings=[])),
    ) as subgraph_mock:
        result = await extract("some text", Paradigm.HSS, paper_id="paper-001")

    subgraph_mock.assert_awaited_once()
    assert result.graph.paper_id == "paper-001"
    assert result.graph.paradigm == Paradigm.HSS
    assert result.warnings == []


@pytest.mark.asyncio
async def test_extract_two_phase_falls_back_to_heuristic(two_phase_live_env: None) -> None:
    """Sub-graph failure with fallback enabled degrades to heuristic graph."""
    _ = two_phase_live_env

    with patch(
        "backend.graph.extract_workflow.run_extract_subgraph",
        new=AsyncMock(side_effect=RuntimeError("structured output failed")),
    ):
        result = await extract("Title: Example\nWe argue that example works.", Paradigm.HSS, paper_id="paper-002")

    assert result.graph.paper_id == "paper-002"
    assert result.graph.paradigm == Paradigm.HSS
    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings


@pytest.mark.asyncio
async def test_extract_two_phase_raises_without_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sub-graph failure with fallback disabled raises ServiceError."""
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("EXTRACT_TWO_PHASE_ENABLED", "true")
    monkeypatch.setenv("EXTRACT_HEURISTIC_FALLBACK", "false")
    get_settings.cache_clear()
    reset_llm_client_cache()

    with (
        patch(
            "backend.graph.extract_workflow.run_extract_subgraph",
            new=AsyncMock(side_effect=RuntimeError("structured output failed")),
        ),
        pytest.raises(ServiceError) as exc_info,
    ):
        await extract("Title: Example", Paradigm.HSS, paper_id="paper-003")

    assert exc_info.value.code == PIPELINE_FAILED_CODE
    assert "图谱 LLM 抽取失败" in exc_info.value.message
