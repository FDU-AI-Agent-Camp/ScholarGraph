"""F.6 acceptance gate T9: pipeline reaches ready after extract fallback."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE
from backend.config import get_settings
from backend.graph.workflow import run_paper_pipeline
from backend.llm.client import reset_llm_client_cache
from backend.schemas.paper import PaperStatus
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.agent_service import AgentService
from backend.services.paper_service import get_paper_service

from tests.conftest import mock_pipeline_node_services
from tests.helpers.f33_hss_graphs import assert_hss_excludes_stem_only_node_types, assert_hss_schema_whitelist

pytestmark = pytest.mark.integration

HSS_SAMPLE = (
    "标题：近代口岸制度研究\n"
    "本文认为通商口岸体现制度路径依赖。\n"
    "首先，口岸开放重塑了地方治理结构。\n"
    "其次，贸易规则形成了路径锁定。\n"
    "历史制度主义视角下分析通商口岸档案。"
)


@pytest.fixture
def live_extract_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("EXTRACT_LLM_ENABLED", "true")
    monkeypatch.setenv("EXTRACT_HEURISTIC_FALLBACK", "true")
    get_settings.cache_clear()
    reset_llm_client_cache()


@pytest.mark.asyncio
async def test_t9_pipeline_llm_fallback_reaches_ready_with_extract_warnings(
    integration_paper: tuple[str, Path],
    live_extract_env: None,
) -> None:
    """T9: real AgentService + LLM failure → status=ready, not failed."""
    _ = live_extract_env
    paper_id, pdf_path = integration_paper
    agent = AgentService()
    agent.classify_paradigm = AsyncMock(  # type: ignore[method-assign]
        return_value=ParadigmClassification(paradigm=Paradigm.HSS, confidence=0.9, reason="mock"),
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
                new=AsyncMock(side_effect=RuntimeError("structured output failed")),
            ),
        ):
            final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("failed") is not True
    assert EXTRACT_HEURISTIC_FALLBACK_CODE in final.get("extract_warnings", [])

    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.READY
    assert status.extract_warnings == [EXTRACT_HEURISTIC_FALLBACK_CODE]

    graph = await get_paper_service().get_graph(paper_id)
    assert_hss_schema_whitelist(graph)
    assert_hss_excludes_stem_only_node_types(graph)

    get_settings.cache_clear()
    reset_llm_client_cache()
