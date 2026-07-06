"""Phase F: extract_warnings on PaperStatusData and GET /papers/{id}/status."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE
from backend.main import app
from backend.rag.handlers import RAG_INDEX_WARNING_CODE, index_paper_for_rag
from backend.schemas.graph import GraphNode, NodeType, UnifiedPaperGraph
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.schemas.paradigm import Paradigm
from backend.services.paper_service import get_paper_service
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def api_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def sample_graph() -> UnifiedPaperGraph:
    return UnifiedPaperGraph(
        paper_id="paper-1",
        paradigm=Paradigm.STEM,
        nodes=[GraphNode(id="n_method", label="Hybrid chunker", type=NodeType.METHOD, data={})],
        edges=[],
    )


class FailingVectorStore:
    """Minimal stand-in that raises on replace_paper_index."""

    def __init__(self) -> None:
        pass

    async def replace_paper_index(
        self,
        _paper_id: str,
        *,
        chunks: list[Any],
        entities: list[Any],
        relations: list[Any],
    ) -> None:
        del chunks, entities, relations
        raise RuntimeError("embedding service unreachable")


@pytest.mark.asyncio
async def test_rag_index_failure_writes_exact_machine_code_to_status(
    sample_graph: UnifiedPaperGraph,
    registered_paper: str,
    monkeypatch: Any,
    caplog: Any,
) -> None:
    """Contract panic test: DB-visible extract_warnings must be a pure machine code."""

    paper_id = registered_paper
    monkeypatch.setattr("backend.rag.handlers.get_paper_service", get_paper_service)

    with caplog.at_level(logging.ERROR, logger="backend.rag.handlers"):
        result = await index_paper_for_rag(
            paper_id,
            full_text="Methods\nWe propose a hybrid chunker.",
            graph=sample_graph,
            vector_store=FailingVectorStore(),
            suppress_errors=True,
        )

    assert result is False

    status = await get_paper_service().get_status(paper_id)
    assert RAG_INDEX_WARNING_CODE in status.extract_warnings

    # Strict cleanliness guarantee: no dynamic error context leaked into codes.
    for warning in status.extract_warnings:
        assert ":" not in warning
        assert "[" not in warning
        assert "]" not in warning

    # Detailed diagnostics remain available in structured logs for operators.
    error_record = next(record for record in caplog.records if RAG_INDEX_WARNING_CODE in record.message)
    assert error_record.exc_type == "RuntimeError"
    assert "embedding service unreachable" in error_record.exc_msg


@pytest.mark.asyncio
async def test_record_extract_warnings_merges_without_duplicates(registered_paper: str) -> None:
    service = get_paper_service()
    service.record_extract_warnings(registered_paper, [EXTRACT_HEURISTIC_FALLBACK_CODE])
    service.record_extract_warnings(
        registered_paper,
        [EXTRACT_HEURISTIC_FALLBACK_CODE, "other_code"],
    )

    status = await service.get_status(registered_paper)

    assert status.extract_warnings == [EXTRACT_HEURISTIC_FALLBACK_CODE, "other_code"]


@pytest.mark.asyncio
async def test_get_status_includes_extract_warnings_after_record(registered_paper: str) -> None:
    service = get_paper_service()
    service.record_extract_warnings(registered_paper, [EXTRACT_HEURISTIC_FALLBACK_CODE])

    status = await service.get_status(registered_paper)

    assert status.extract_warnings == [EXTRACT_HEURISTIC_FALLBACK_CODE]


@pytest.mark.asyncio
async def test_status_snapshot_carries_extract_warnings_on_stage_advance(registered_paper: str) -> None:
    service = get_paper_service()
    service.record_extract_warnings(registered_paper, [EXTRACT_HEURISTIC_FALLBACK_CODE])
    service.set_status_snapshot(
        registered_paper,
        status=PaperStatus.READY,
        stage=PipelineStage.READY,
        percent=100,
        message="建图完成",
    )

    status = await service.get_status(registered_paper)

    assert status.stage == PipelineStage.READY
    assert status.extract_warnings == [EXTRACT_HEURISTIC_FALLBACK_CODE]


@pytest.mark.asyncio
async def test_status_api_returns_extract_warnings(
    api_client: AsyncClient,
    registered_paper: str,
) -> None:
    paper_id = registered_paper
    get_paper_service().record_extract_warnings(paper_id, [EXTRACT_HEURISTIC_FALLBACK_CODE])

    response = await api_client.get(f"/api/v1/papers/{paper_id}/status")

    assert response.status_code == 200
    assert response.json()["data"]["extract_warnings"] == [EXTRACT_HEURISTIC_FALLBACK_CODE]


@pytest.mark.asyncio
async def test_get_paper_includes_extract_warnings_on_detail(registered_paper: str) -> None:
    service = get_paper_service()
    service.record_extract_warnings(registered_paper, [EXTRACT_HEURISTIC_FALLBACK_CODE])

    paper = await service.get_paper(registered_paper)

    assert paper.extract_warnings == [EXTRACT_HEURISTIC_FALLBACK_CODE]
