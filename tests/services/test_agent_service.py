"""Functional and error-mapping tests for AgentService."""

from unittest.mock import AsyncMock, patch

import pytest

from backend.schemas.graph import GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.agent_service import AgentService
from backend.services.errors import ServiceError


async def test_classify_paradigm_success() -> None:
    expected = ParadigmClassification(
        paradigm=Paradigm.STEM,
        confidence=0.8,
        reason="量化实验",
    )
    service = AgentService()
    with patch("backend.services.agent_service.classify", new_callable=AsyncMock) as raw:
        raw.return_value = expected
        result = await service.classify_paradigm("abstract text")

    raw.assert_awaited_once_with("abstract text")
    assert result.paradigm == Paradigm.STEM


@pytest.mark.parametrize(
    ("method", "call"),
    [
        ("classify_paradigm", lambda s: s.classify_paradigm("x")),
        ("extract_graph", lambda s: s.extract_graph("text", Paradigm.HSS, paper_id="pid")),
    ],
)
async def test_agent_not_implemented_maps_pipeline_failed(
    method: str,
    call,
) -> None:
    service = AgentService()
    target = "backend.services.agent_service.classify" if method == "classify_paradigm" else "backend.services.agent_service.extract"
    with patch(target, new_callable=AsyncMock) as raw:
        raw.side_effect = NotImplementedError(f"BE-2 {method}")
        with pytest.raises(ServiceError) as err:
            await call(service)
    assert err.value.code == "PIPELINE_FAILED"


@pytest.mark.parametrize(
    ("method", "call"),
    [
        ("classify_paradigm", lambda s: s.classify_paradigm("x")),
        ("extract_graph", lambda s: s.extract_graph("text", Paradigm.HSS, paper_id="pid")),
    ],
)
async def test_agent_runtime_error_maps_llm_json_invalid(method: str, call) -> None:
    service = AgentService()
    target = "backend.services.agent_service.classify" if method == "classify_paradigm" else "backend.services.agent_service.extract"
    with patch(target, new_callable=AsyncMock) as raw:
        raw.side_effect = RuntimeError("bad json")
        with pytest.raises(ServiceError) as err:
            await call(service)
    assert err.value.code == "LLM_JSON_INVALID"


async def test_extract_graph_aligns_paper_id_and_paradigm() -> None:
    service = AgentService()
    raw_graph = UnifiedPaperGraph(
        paper_id="wrong",
        paradigm=Paradigm.STEM,
        nodes=[GraphNode(id="n1", label="n", type="Thesis")],
        edges=[],
    )
    with patch("backend.services.agent_service.extract", new_callable=AsyncMock) as raw:
        raw.return_value = raw_graph
        graph = await service.extract_graph("body", Paradigm.HSS, paper_id="correct-id")

    assert graph.paper_id == "correct-id"
    assert graph.paradigm == Paradigm.HSS
