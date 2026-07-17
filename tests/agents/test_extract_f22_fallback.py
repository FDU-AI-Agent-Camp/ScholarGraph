# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Phase F.2.2 acceptance: heuristic fallback (X9–X12)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from backend.agents import extract_heuristic
from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE
from backend.agents.extractor import extract
from backend.config import get_settings
from backend.llm.client import reset_llm_client_cache
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm

HSS_SAMPLE = "标题：近代口岸研究\n本文认为通商口岸体现制度路径依赖。"
STEM_SAMPLE = "Title: Benchmark\nWe evaluate accuracy on datasets against baselines."


def _hss_llm_graph(**updates: object) -> UnifiedPaperGraph:
    base = UnifiedPaperGraph(
        paper_id="ignored",
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="核心论点", type="Thesis")],
        edges=[GraphEdge(id="e1", source="n1", target="n1", label="REF", type="REF")],
        summary="llm",
    )
    if updates:
        return base.model_copy(update=updates)
    return base


@pytest.fixture
def live_extract_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("EXTRACT_LLM_ENABLED", "true")
    monkeypatch.setenv("EXTRACT_HEURISTIC_FALLBACK", "true")
    get_settings.cache_clear()
    reset_llm_client_cache()


@pytest.mark.parametrize(
    ("side_effect", "label"),
    [
        (TimeoutError("api timeout"), "api_timeout"),
        (ConnectionError("network down"), "network_error"),
        (RuntimeError("with_structured_output failed"), "structured_output"),
        (ValueError("json/schema invalid"), "schema_validation"),
    ],
)
@pytest.mark.asyncio
async def test_x9_llm_failures_trigger_heuristic_fallback(
    live_extract_env: None,
    side_effect: Exception,
    label: str,
) -> None:
    _ = live_extract_env
    with patch(
        "backend.agents.extractor.extract_with_llm",
        new=AsyncMock(side_effect=side_effect),
    ):
        result = await extract(HSS_SAMPLE, Paradigm.HSS, paper_id=f"paper-x9-{label}")

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings
    assert result.graph.paper_id == f"paper-x9-{label}"
    assert any(node.type == "Thesis" for node in result.graph.nodes)
    assert "启发式 fallback" in (result.graph.summary or "")


@pytest.mark.asyncio
async def test_x9_empty_nodes_triggers_fallback(live_extract_env: None) -> None:
    _ = live_extract_env
    empty_graph = UnifiedPaperGraph(
        paper_id="p",
        paradigm=Paradigm.HSS,
        nodes=[],
        edges=[],
    )
    with patch(
        "backend.agents.extract_llm._invoke_structured",
        new=AsyncMock(return_value=empty_graph),
    ):
        result = await extract(HSS_SAMPLE, Paradigm.HSS, paper_id="paper-x9-empty-nodes")

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings
    assert result.graph.nodes


@pytest.mark.asyncio
async def test_x9_empty_edges_triggers_fallback(live_extract_env: None) -> None:
    _ = live_extract_env
    no_edges = UnifiedPaperGraph(
        paper_id="p",
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="论点", type="Thesis")],
        edges=[],
    )
    with patch(
        "backend.agents.extract_llm._invoke_structured",
        new=AsyncMock(return_value=no_edges),
    ):
        result = await extract(HSS_SAMPLE, Paradigm.HSS, paper_id="paper-x9-empty-edges")

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings
    assert result.graph.edges


@pytest.mark.asyncio
async def test_x10_fallback_dispatches_hss_and_stem_builders(live_extract_env: None) -> None:
    _ = live_extract_env
    with (
        patch(
            "backend.agents.extractor.extract_with_llm",
            new=AsyncMock(side_effect=RuntimeError("llm down")),
        ),
        patch(
            "backend.agents.extractor.build_heuristic_graph",
            wraps=extract_heuristic.build_heuristic_graph,
        ) as heuristic_mock,
    ):
        hss_result = await extract(HSS_SAMPLE, Paradigm.HSS, paper_id="paper-x10-hss")
        stem_result = await extract(STEM_SAMPLE, Paradigm.STEM, paper_id="paper-x10-stem")

    assert heuristic_mock.call_count == 2
    assert hss_result.graph.paradigm == Paradigm.HSS
    assert stem_result.graph.paradigm == Paradigm.STEM
    assert any(node.type == "Thesis" for node in hss_result.graph.nodes)
    assert any(node.type == "Method" for node in stem_result.graph.nodes)


@pytest.mark.asyncio
async def test_x11_agent_service_fallback_does_not_raise(live_extract_env: None) -> None:
    _ = live_extract_env
    from backend.services.agent_service import AgentService

    with patch(
        "backend.agents.extractor.extract_with_llm",
        new=AsyncMock(side_effect=TimeoutError("api timeout")),
    ):
        result = await AgentService().extract_graph(HSS_SAMPLE, Paradigm.HSS, paper_id="paper-x11-svc")

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings
    assert result.graph.paper_id == "paper-x11-svc"


@pytest.mark.asyncio
async def test_x12_extract_llm_fallback_log_emitted(
    live_extract_env: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _ = live_extract_env
    caplog.set_level("WARNING", logger="backend.agents.extractor")

    with patch(
        "backend.agents.extractor.extract_with_llm",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        await extract(HSS_SAMPLE, Paradigm.HSS, paper_id="paper-x12-log")

    records = [record for record in caplog.records if record.getMessage() == "extract_llm_fallback"]
    assert len(records) == 1
    assert getattr(records[0], "paper_id", None) == "paper-x12-log"
    assert "boom" in str(getattr(records[0], "reason", ""))
