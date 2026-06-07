"""F.2.3 integration: fallback warnings on status + PaperDetail after pipeline (X16–X17)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
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

HSS_SAMPLE = "标题：近代口岸研究\n本文认为通商口岸体现制度路径依赖。"


@pytest.fixture
def live_extract_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
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
async def test_x16_x17_pipeline_fallback_warnings_on_status_and_detail(
    integration_paper: tuple[str, Path],
    live_extract_env: None,
    api_client: AsyncClient,
) -> None:
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

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in final.get("extract_warnings", [])

    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.READY
    assert status.extract_warnings == [EXTRACT_HEURISTIC_FALLBACK_CODE]

    paper = await get_paper_service().get_paper(paper_id)
    assert paper.extract_warnings == [EXTRACT_HEURISTIC_FALLBACK_CODE]

    status_resp = await api_client.get(f"/api/v1/papers/{paper_id}/status")
    detail_resp = await api_client.get(f"/api/v1/papers/{paper_id}")

    assert status_resp.status_code == 200
    assert detail_resp.status_code == 200
    assert status_resp.json()["data"]["extract_warnings"] == [EXTRACT_HEURISTIC_FALLBACK_CODE]
    assert detail_resp.json()["data"]["extract_warnings"] == [EXTRACT_HEURISTIC_FALLBACK_CODE]


@pytest.mark.asyncio
async def test_x19_pipeline_success_has_empty_extract_warnings_on_status_and_detail(
    integration_paper: tuple[str, Path],
    live_extract_env: None,
) -> None:
    _ = live_extract_env
    paper_id, pdf_path = integration_paper
    from backend.agents.extract_types import ExtractResult
    from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph

    graph = UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="Thesis", type="Thesis")],
        edges=[GraphEdge(id="e1", source="n1", target="n1", label="REF", type="REF")],
    )

    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["agent"].extract_graph = AsyncMock(return_value=ExtractResult(graph=graph, warnings=[]))
        final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("extract_warnings", []) == []

    status = await get_paper_service().get_status(paper_id)
    paper = await get_paper_service().get_paper(paper_id)
    assert status.extract_warnings == []
    assert paper.extract_warnings == []
