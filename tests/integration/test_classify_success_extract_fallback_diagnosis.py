# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Integration: classify success + extract heuristic fallback diagnosis."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from backend.agents.classifier_types import ClassifyResult
from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE
from backend.config import get_settings
from backend.graph.workflow import run_paper_pipeline
from backend.llm.client import reset_llm_client_cache
from backend.main import app
from backend.schemas.paper import PaperStatus
from backend.schemas.paradigm import Paradigm, ParadigmClassification
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
def live_both_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("CLASSIFIER_LLM_ENABLED", "true")
    monkeypatch.setenv("CLASSIFIER_HEURISTIC_FALLBACK", "true")
    monkeypatch.setenv("EXTRACT_LLM_ENABLED", "true")
    monkeypatch.setenv("EXTRACT_HEURISTIC_FALLBACK", "true")
    get_settings.cache_clear()
    reset_llm_client_cache()


@pytest.fixture
async def api_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_pipeline_classify_success_extract_fallback_status_split(
    integration_paper: tuple[str, Path],
    live_both_llm_env: None,
    api_client: AsyncClient,
) -> None:
    """范式分类成功 + 图谱抽取 fallback：classify_warnings 空，extract_warnings 有码。"""
    _ = live_both_llm_env
    paper_id, pdf_path = integration_paper
    agent = AgentService()
    classification = ParadigmClassification(
        paradigm=Paradigm.STEM,
        confidence=0.91,
        reason="LLM classify success.",
    )

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
                new=AsyncMock(return_value=classification),
            ),
            patch(
                "backend.agents.extractor.extract_with_llm",
                new=AsyncMock(side_effect=RuntimeError("structured output failed")),
            ),
        ):
            final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("failed") is not True
    assert final.get("classify_warnings", []) == []
    assert EXTRACT_HEURISTIC_FALLBACK_CODE in final.get("extract_warnings", [])

    status = await get_paper_service().get_status(paper_id)
    paper = await get_paper_service().get_paper(paper_id)

    assert status.status == PaperStatus.READY
    assert status.classify_warnings == []
    assert status.extract_warnings == [EXTRACT_HEURISTIC_FALLBACK_CODE]
    assert paper.classify_warnings == []
    assert paper.extract_warnings == [EXTRACT_HEURISTIC_FALLBACK_CODE]

    status_resp = await api_client.get(f"/api/v1/papers/{paper_id}/status")
    detail_resp = await api_client.get(f"/api/v1/papers/{paper_id}")

    assert status_resp.json()["data"]["classify_warnings"] == []
    assert status_resp.json()["data"]["extract_warnings"] == [EXTRACT_HEURISTIC_FALLBACK_CODE]
    assert detail_resp.json()["data"]["classify_warnings"] == []
    assert detail_resp.json()["data"]["extract_warnings"] == [EXTRACT_HEURISTIC_FALLBACK_CODE]


@pytest.mark.asyncio
async def test_pipeline_extract_disabled_classify_llm_success(
    integration_paper: tuple[str, Path],
    live_both_llm_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EXTRACT_LLM_ENABLED=false：分类 LLM 成功仍会导致 extract fallback（常见误配）。"""
    _ = live_both_llm_env
    paper_id, pdf_path = integration_paper
    agent = AgentService()
    classification = ParadigmClassification(
        paradigm=Paradigm.STEM,
        confidence=0.9,
        reason="Classify ok.",
    )

    monkeypatch.setenv("EXTRACT_LLM_ENABLED", "false")
    get_settings.cache_clear()
    reset_llm_client_cache()

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
                new=AsyncMock(return_value=classification),
            ),
            patch("backend.agents.extractor.extract_with_llm", new=AsyncMock()) as extract_llm_mock,
        ):
            final = await run_paper_pipeline(paper_id, pdf_path)

    extract_llm_mock.assert_not_awaited()
    assert final.get("classify_warnings", []) == []
    assert EXTRACT_HEURISTIC_FALLBACK_CODE in final.get("extract_warnings", [])


@pytest.mark.asyncio
async def test_pipeline_both_llm_success_has_no_fallback_warnings(
    integration_paper: tuple[str, Path],
    live_both_llm_env: None,
) -> None:
    """对照：分类与抽取均 LLM 成功时不应出现任一 fallback 机器码。"""
    from tests.agents.conftest import minimal_valid_llm_graph

    _ = live_both_llm_env
    paper_id, pdf_path = integration_paper
    classification = ParadigmClassification(
        paradigm=Paradigm.STEM,
        confidence=0.92,
        reason="Classify ok.",
    )
    llm_graph = minimal_valid_llm_graph(paper_id=paper_id, paradigm=Paradigm.STEM)

    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["agent"].classify_paradigm = AsyncMock(
            return_value=ClassifyResult(classification=classification, warnings=[]),
        )
        mocks["agent"].extract_graph = AsyncMock(
            return_value=__import__(
                "backend.agents.extract_types",
                fromlist=["ExtractResult"],
            ).ExtractResult(graph=llm_graph, warnings=[]),
        )
        final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("classify_warnings", []) == []
    assert final.get("extract_warnings", []) == []

    status = await get_paper_service().get_status(paper_id)
    assert status.classify_warnings == []
    assert status.extract_warnings == []
