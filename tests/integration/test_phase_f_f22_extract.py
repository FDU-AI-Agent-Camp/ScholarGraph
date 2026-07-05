"""F.2.2 integration: real extractor fallback through LangGraph pipeline (X11)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from backend.agents.classifier_types import ClassifyResult
from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE
from backend.config import get_settings
from backend.graph.workflow import run_paper_pipeline
from backend.llm.client import reset_llm_client_cache
from backend.schemas.paper import PaperStatus
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.agent_service import AgentService
from backend.services.paper_service import get_paper_service

from tests.conftest import mock_pipeline_node_services

pytestmark = pytest.mark.integration

HSS_SAMPLE = "标题：近代口岸研究\n本文认为通商口岸体现制度路径依赖。"


@pytest.fixture
def live_extract_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("EXTRACT_LLM_ENABLED", "true")
    monkeypatch.setenv("EXTRACT_HEURISTIC_FALLBACK", "true")
    get_settings.cache_clear()
    reset_llm_client_cache()


@pytest.mark.asyncio
async def test_x11_live_fallback_pipeline_reaches_ready(
    integration_paper: tuple[str, Path],
    live_extract_env: None,
) -> None:
    _ = live_extract_env
    paper_id, pdf_path = integration_paper
    classification = ParadigmClassification(paradigm=Paradigm.HSS, confidence=0.9, reason="mock")

    agent = AgentService()
    agent.classify_paradigm = AsyncMock(  # type: ignore[method-assign]
        return_value=ClassifyResult(classification=classification, warnings=[]),
    )

    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["ingest"].ingest = AsyncMock(
            return_value={
                "paper_id": paper_id,
                "full_text": HSS_SAMPLE,
                "classifier_input": "snippet",
            },
        )
        with (
            patch("backend.graph.nodes.get_agent_service", return_value=agent),
            patch(
                "backend.agents.extractor.extract_with_llm",
                new=AsyncMock(side_effect=TimeoutError("api timeout")),
            ),
        ):
            final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("failed") is not True
    assert EXTRACT_HEURISTIC_FALLBACK_CODE in final.get("extract_warnings", [])
    mocks["store_save"].assert_called_once()

    saved = mocks["store_save"].call_args.args[0]
    assert saved.paper_id == paper_id
    assert any(node.type == "Thesis" for node in saved.nodes)
    assert "启发式 fallback" in (saved.summary or "")

    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.READY
    assert EXTRACT_HEURISTIC_FALLBACK_CODE in status.extract_warnings
    # Fine-grained root-cause code is surfaced alongside the generic fallback code.
    assert any("extract_llm_" in code for code in status.extract_warnings)


@pytest.mark.asyncio
async def test_x11_extract_node_not_failed_on_llm_timeout(
    integration_paper: tuple[str, Path],
    live_extract_env: None,
) -> None:
    _ = live_extract_env
    paper_id, pdf_path = integration_paper
    agent = AgentService()
    agent.classify_paradigm = AsyncMock(  # type: ignore[method-assign]
        return_value=ClassifyResult(
            classification=ParadigmClassification(paradigm=Paradigm.STEM, confidence=0.9, reason="mock"),
            warnings=[],
        ),
    )

    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["ingest"].ingest = AsyncMock(
            return_value={
                "paper_id": paper_id,
                "full_text": "Title: Benchmark\nmethod dataset benchmark accuracy baseline",
                "classifier_input": "snippet",
            },
        )
        with (
            patch("backend.graph.nodes.get_agent_service", return_value=agent),
            patch(
                "backend.agents.extractor.extract_with_llm",
                new=AsyncMock(side_effect=ConnectionError("network down")),
            ),
        ):
            final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("failed") is not True
    assert final.get("stage") != "failed"
    assert EXTRACT_HEURISTIC_FALLBACK_CODE in final.get("extract_warnings", [])
