"""F.2.1 integration: real AgentService extract through pipeline wiring."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE
from backend.config import get_settings
from backend.graph.workflow import run_paper_pipeline
from backend.llm.client import reset_llm_client_cache
from backend.schemas.graph import GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperStatus
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.paper_service import get_paper_service

from tests.conftest import mock_pipeline_node_services

pytestmark = pytest.mark.integration


@pytest.fixture
def live_extract_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Live extract path: LLM main + heuristic fallback enabled."""
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("EXTRACT_LLM_ENABLED", "true")
    monkeypatch.setenv("EXTRACT_HEURISTIC_FALLBACK", "true")
    get_settings.cache_clear()
    reset_llm_client_cache()


def _llm_graph(paper_id: str, paradigm: Paradigm) -> UnifiedPaperGraph:
    node_type = "Thesis" if paradigm == Paradigm.HSS else "Method"
    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=paradigm,
        nodes=[GraphNode(id="n1", label="core", type=node_type)],
        edges=[],
        summary="llm",
    )


async def _run_with_real_agent_service(
    paper_id: str,
    pdf_path: Path,
    *,
    extract_with_llm_mock: AsyncMock,
    classification: ParadigmClassification | None = None,
    ingest_full_text: str | None = None,
):
    from backend.services.agent_service import AgentService

    agent = AgentService()
    if classification is not None:
        agent.classify_paradigm = AsyncMock(return_value=classification)  # type: ignore[method-assign]

    with mock_pipeline_node_services(paper_id) as mocks:
        if ingest_full_text is not None:
            mocks["ingest"].ingest = AsyncMock(
                return_value={
                    "paper_id": paper_id,
                    "full_text": ingest_full_text,
                    "classifier_input": "snippet",
                },
            )
        with (
            patch("backend.graph.nodes.get_agent_service", return_value=agent),
            patch("backend.agents.extractor.extract_with_llm", new=extract_with_llm_mock),
        ):
            final = await run_paper_pipeline(paper_id, pdf_path)
        return final, mocks


@pytest.mark.asyncio
async def test_f21_pipeline_llm_success_no_extract_warnings(
    integration_paper: tuple[str, Path],
    live_extract_env: None,
) -> None:
    _ = live_extract_env
    paper_id, pdf_path = integration_paper
    classification = ParadigmClassification(paradigm=Paradigm.HSS, confidence=0.9, reason="mock")
    llm_mock = AsyncMock(return_value=_llm_graph(paper_id, Paradigm.HSS))

    final, _ = await _run_with_real_agent_service(
        paper_id,
        pdf_path,
        extract_with_llm_mock=llm_mock,
        classification=classification,
    )

    assert final.get("failed") is not True
    assert final.get("extract_warnings", []) == []
    llm_mock.assert_awaited_once()

    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.READY
    assert status.extract_warnings == []


@pytest.mark.asyncio
async def test_f21_pipeline_llm_failure_fallback_reaches_ready_with_warning(
    integration_paper: tuple[str, Path],
    live_extract_env: None,
) -> None:
    _ = live_extract_env
    paper_id, pdf_path = integration_paper
    classification = ParadigmClassification(paradigm=Paradigm.STEM, confidence=0.9, reason="mock")
    llm_mock = AsyncMock(side_effect=RuntimeError("structured output failed"))

    final, _ = await _run_with_real_agent_service(
        paper_id,
        pdf_path,
        extract_with_llm_mock=llm_mock,
        classification=classification,
        ingest_full_text="Title: Benchmark\nWe evaluate accuracy on datasets against baselines.",
    )

    assert final.get("failed") is not True
    assert EXTRACT_HEURISTIC_FALLBACK_CODE in final.get("extract_warnings", [])

    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.READY
    assert status.extract_warnings == [EXTRACT_HEURISTIC_FALLBACK_CODE]


@pytest.mark.asyncio
async def test_f21_pipeline_uses_real_agent_service_extract_graph(
    integration_paper: tuple[str, Path],
    live_extract_env: None,
) -> None:
    _ = live_extract_env
    """Ensure extract_node hits AgentService → extractor (not a stub graph)."""
    paper_id, pdf_path = integration_paper
    llm_mock = AsyncMock(return_value=_llm_graph(paper_id, Paradigm.HSS))

    _final, mocks = await _run_with_real_agent_service(  # noqa: RUF059
        paper_id,
        pdf_path,
        extract_with_llm_mock=llm_mock,
        classification=ParadigmClassification(paradigm=Paradigm.HSS, confidence=0.9, reason="x"),
    )

    saved = mocks["store_save"].call_args.args[0]
    assert saved.paper_id == paper_id
    assert saved.summary == "llm"
