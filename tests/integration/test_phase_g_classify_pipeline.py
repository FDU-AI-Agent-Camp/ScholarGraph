"""Phase G integration: classify fallback warnings on status + PaperDetail after pipeline."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from backend.agents.classifier_constants import CLASSIFIER_HEURISTIC_FALLBACK_CODE
from backend.config import get_settings
from backend.graph.workflow import run_paper_pipeline
from backend.llm.client import reset_llm_client_cache
from backend.main import app
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.services.agent_service import AgentService
from backend.services.paper_service import get_paper_service
from httpx import ASGITransport, AsyncClient

from tests.conftest import mock_pipeline_node_services

pytestmark = pytest.mark.integration

STEM_SNIPPET = (
    "Title: Agent framework benchmark. We evaluate the model on datasets with accuracy, "
    "F1 metrics, baselines, and ablation experiments."
)


@pytest.fixture
def live_classify_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("CLASSIFIER_LLM_ENABLED", "true")
    monkeypatch.setenv("CLASSIFIER_HEURISTIC_FALLBACK", "true")
    monkeypatch.setenv("EXTRACT_LLM_ENABLED", "false")
    get_settings.cache_clear()
    reset_llm_client_cache()


@pytest.fixture
async def api_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_g16_g17_pipeline_classify_fallback_warnings_on_status_and_detail(
    integration_paper: tuple[str, Path],
    live_classify_env: None,
    api_client: AsyncClient,
) -> None:
    _ = live_classify_env
    paper_id, pdf_path = integration_paper
    agent = AgentService()

    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["ingest"].ingest = AsyncMock(
            return_value={
                "paper_id": paper_id,
                "full_text": STEM_SNIPPET,
                "classifier_input": STEM_SNIPPET,
            },
        )
        with (
            patch("backend.graph.nodes.get_agent_service", return_value=agent),
            patch(
                "backend.agents.classifier.classify_with_llm",
                new=AsyncMock(side_effect=RuntimeError("structured output failed")),
            ),
        ):
            final = await run_paper_pipeline(paper_id, pdf_path)

    assert CLASSIFIER_HEURISTIC_FALLBACK_CODE in final.get("classify_warnings", [])

    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.READY
    assert status.classify_warnings == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]

    paper = await get_paper_service().get_paper(paper_id)
    assert paper.classify_warnings == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]

    status_resp = await api_client.get(f"/api/v1/papers/{paper_id}/status")
    detail_resp = await api_client.get(f"/api/v1/papers/{paper_id}")

    assert status_resp.status_code == 200
    assert detail_resp.status_code == 200
    assert status_resp.json()["data"]["classify_warnings"] == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]
    assert detail_resp.json()["data"]["classify_warnings"] == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]


@pytest.mark.asyncio
async def test_g19_pipeline_classify_success_has_empty_classify_warnings(
    integration_paper: tuple[str, Path],
    live_classify_env: None,
) -> None:
    _ = live_classify_env
    paper_id, pdf_path = integration_paper
    from backend.agents.classifier_types import ClassifyResult
    from backend.schemas.paradigm import Paradigm, ParadigmClassification

    classification = ParadigmClassification(
        paradigm=Paradigm.STEM,
        confidence=0.91,
        reason="LLM mock success",
    )

    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["agent"].classify_paradigm = AsyncMock(
            return_value=ClassifyResult(classification=classification, warnings=[]),
        )
        final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("classify_warnings", []) == []

    status = await get_paper_service().get_status(paper_id)
    paper = await get_paper_service().get_paper(paper_id)
    assert status.classify_warnings == []
    assert paper.classify_warnings == []


@pytest.mark.asyncio
async def test_g18_pipeline_classify_failure_without_fallback_marks_failed(
    integration_paper: tuple[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paper_id, pdf_path = integration_paper
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("CLASSIFIER_LLM_ENABLED", "true")
    monkeypatch.setenv("CLASSIFIER_HEURISTIC_FALLBACK", "false")
    get_settings.cache_clear()
    reset_llm_client_cache()

    agent = AgentService()

    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["ingest"].ingest = AsyncMock(
            return_value={
                "paper_id": paper_id,
                "full_text": STEM_SNIPPET,
                "classifier_input": STEM_SNIPPET,
            },
        )
        with (
            patch("backend.graph.nodes.get_agent_service", return_value=agent),
            patch(
                "backend.agents.classifier.classify_with_llm",
                new=AsyncMock(side_effect=RuntimeError("structured output failed")),
            ),
        ):
            final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("failed") is True
    assert final.get("error_code") == "PIPELINE_FAILED"

    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.FAILED
    assert status.failed_during == PipelineStage.CLASSIFYING
    assert status.classify_warnings == []


@pytest.mark.asyncio
async def test_g24_pipeline_llm_disabled_writes_classify_warnings(
    integration_paper: tuple[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paper_id, pdf_path = integration_paper
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("CLASSIFIER_LLM_ENABLED", "false")
    monkeypatch.setenv("CLASSIFIER_HEURISTIC_FALLBACK", "true")
    monkeypatch.setenv("EXTRACT_LLM_ENABLED", "false")
    get_settings.cache_clear()
    reset_llm_client_cache()

    agent = AgentService()

    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["ingest"].ingest = AsyncMock(
            return_value={
                "paper_id": paper_id,
                "full_text": STEM_SNIPPET,
                "classifier_input": STEM_SNIPPET,
            },
        )
        with (
            patch("backend.graph.nodes.get_agent_service", return_value=agent),
            patch("backend.agents.classifier.classify_with_llm", new=AsyncMock()) as llm_mock,
        ):
            final = await run_paper_pipeline(paper_id, pdf_path)

    llm_mock.assert_not_awaited()
    assert final.get("failed") is not True
    assert CLASSIFIER_HEURISTIC_FALLBACK_CODE in final.get("classify_warnings", [])

    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.READY
    assert status.classify_warnings == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]
