"""Functional and error-mapping tests for AgentService."""

from unittest.mock import AsyncMock, patch

import pytest
from backend.agents.classifier_types import ClassifyResult
from backend.agents.extract_types import ExtractResult
from backend.schemas.graph import GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.agent_service import AgentService
from backend.services.errors import ServiceError


def _agent_be_patch_target(method: str) -> str:
    if method == "classify_paradigm":
        return "backend.services.agent_service.classify"
    return "backend.services.agent_service.extract"


async def test_classify_paradigm_success() -> None:
    expected = ParadigmClassification(
        paradigm=Paradigm.STEM,
        confidence=0.8,
        reason="量化实验",
    )
    service = AgentService()
    with patch("backend.services.agent_service.classify", new_callable=AsyncMock) as raw:
        raw.return_value = ClassifyResult(classification=expected, warnings=[])
        result = await service.classify_paradigm("abstract text")

    raw.assert_awaited_once_with("abstract text")
    assert result.classification.paradigm == Paradigm.STEM


async def test_classify_paradigm_propagates_service_error() -> None:
    service = AgentService()
    with patch("backend.services.agent_service.classify", new_callable=AsyncMock) as raw:
        raw.side_effect = ServiceError("PIPELINE_FAILED", "范式 LLM 分类失败")
        with pytest.raises(ServiceError) as err:
            await service.classify_paradigm("x")
    assert err.value.code == "PIPELINE_FAILED"


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
    with patch(_agent_be_patch_target(method), new_callable=AsyncMock) as raw:
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
    with patch(_agent_be_patch_target(method), new_callable=AsyncMock) as raw:
        raw.side_effect = RuntimeError("bad json")
        with pytest.raises(ServiceError) as err:
            await call(service)
    assert err.value.code == "LLM_JSON_INVALID"


async def test_extract_graph_delegates_to_extract_with_paper_id() -> None:
    service = AgentService()
    expected = ExtractResult(
        graph=UnifiedPaperGraph(
            paper_id="correct-id",
            paradigm=Paradigm.HSS,
            nodes=[GraphNode(id="n1", label="n", type="Thesis")],
            edges=[],
        ),
        warnings=["extract_heuristic_fallback"],
    )
    with patch("backend.services.agent_service.extract", new_callable=AsyncMock) as raw:
        raw.return_value = expected
        result = await service.extract_graph("body", Paradigm.HSS, paper_id="correct-id")

    raw.assert_awaited_once_with("body", Paradigm.HSS, paper_id="correct-id")
    assert result is expected
