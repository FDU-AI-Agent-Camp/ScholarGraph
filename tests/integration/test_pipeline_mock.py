# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""
端到端流水线集成测试（Mock BE-1～3，不调用真实 LLM / PDF 解析）。

对应 handoff：tests/integration/test_pipeline_mock.py
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.agents.classifier_types import ClassifyResult
from backend.agents.workflow import run_paper_pipeline
from backend.graph.state import NODE_CLASSIFY, NODE_EXTRACT, NODE_INGEST, NODE_STORE, STAGE_PERCENT
from backend.graph.workflow import run_paper_pipeline as run_paper_pipeline_from_graph
from backend.rag.vector_store import VectorStore
from backend.schemas.graph import GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.errors import ServiceError
from backend.services.paper_service import get_paper_service

from tests.conftest import mock_pipeline_node_services
from tests.helpers.event_bus_testkit import drain_event_bus
from tests.helpers.status_contract import assert_snapshot_matches_contract

pytestmark = pytest.mark.integration


class _InMemoryRagRunTracker:
    """Avoid sync DB bridge calls from async EventBus handlers during integration tests."""

    def __init__(self) -> None:
        self._active_run_ids: dict[str, str] = {}

    async def get_active_run_id(self, paper_id: str) -> str | None:
        return self._active_run_ids.get(paper_id)

    async def set_active_run_id(self, paper_id: str, run_id: str) -> None:
        self._active_run_ids[paper_id] = run_id


async def test_run_paper_pipeline_success_mock_e2e(integration_paper: tuple[str, Path]) -> None:
    paper_id, pdf_path = integration_paper

    with mock_pipeline_node_services(paper_id):
        final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("failed") is not True
    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.READY
    assert status.error_code is None
    assert status.failed_during is None
    assert_snapshot_matches_contract(status)

    graph = await get_paper_service().get_graph(paper_id)
    assert graph.paper_id == paper_id


def test_agents_workflow_reexports_run_paper_pipeline() -> None:
    """``backend.agents.workflow`` 与 ``backend.graph.workflow`` 导出同一协程入口。"""
    assert run_paper_pipeline is run_paper_pipeline_from_graph


async def test_run_paper_pipeline_failure_persists_error_fields(
    integration_paper: tuple[str, Path],
) -> None:
    paper_id, pdf_path = integration_paper

    ingest_svc = MagicMock()
    ingest_svc.ingest = AsyncMock(
        side_effect=ServiceError("INGEST_FAILED", "无法解析 PDF: corrupt"),
    )

    with patch("backend.graph.nodes.get_ingest_service", return_value=ingest_svc):
        final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("failed") is True
    assert final.get("error_code") == "INGEST_FAILED"

    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.FAILED
    assert status.stage == PipelineStage.FAILED
    assert status.percent == 0
    assert status.error_code == "INGEST_FAILED"
    assert status.failed_during == PipelineStage.INGESTING
    assert "无法解析" in status.message
    assert_snapshot_matches_contract(status)


async def test_run_paper_pipeline_classify_failure_error_code(
    integration_paper: tuple[str, Path],
) -> None:
    paper_id, pdf_path = integration_paper

    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["agent"].classify_paradigm = AsyncMock(
            side_effect=ServiceError("LLM_JSON_INVALID", "schema mismatch"),
        )
        final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("error_code") == "LLM_JSON_INVALID"
    status = await get_paper_service().get_status(paper_id)
    assert status.error_code == "LLM_JSON_INVALID"
    assert status.failed_during == PipelineStage.CLASSIFYING
    mocks["agent"].extract_graph.assert_not_awaited()


async def test_run_paper_pipeline_startup_then_stage_order(
    integration_paper: tuple[str, Path],
) -> None:
    paper_id, pdf_path = integration_paper
    call_order: list[str] = []
    classification = ParadigmClassification(paradigm=Paradigm.HSS, confidence=0.9, reason="mock")
    graph = UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="N", type="Thesis")],
        edges=[],
    )

    with mock_pipeline_node_services(paper_id) as mocks:

        async def track_ingest(path: Path, *, paper_id: str):
            call_order.append(NODE_INGEST)
            snap = await get_paper_service().get_status(paper_id)
            assert snap.status == PaperStatus.PROCESSING
            assert snap.stage == PipelineStage.INGESTING
            assert snap.percent == STAGE_PERCENT[PipelineStage.INGESTING]
            return {
                "paper_id": paper_id,
                "full_text": "body",
                "classifier_input": "snippet",
            }

        async def track_classify(_text: str):
            call_order.append(NODE_CLASSIFY)
            return ClassifyResult(classification=classification, warnings=[])

        from backend.agents.extract_types import ExtractResult

        async def track_extract(_text: str, _paradigm: Paradigm, *, paper_id: str):
            call_order.append(NODE_EXTRACT)
            return ExtractResult(graph=graph, warnings=[])

        mocks["ingest"].ingest = AsyncMock(side_effect=track_ingest)
        mocks["agent"].classify_paradigm = AsyncMock(side_effect=track_classify)
        mocks["agent"].extract_graph = AsyncMock(side_effect=track_extract)
        original_finalize = mocks["completion"].finalize

        def _track_finalize(*args, **kwargs):
            call_order.append(NODE_STORE)
            return original_finalize(*args, **kwargs)

        mocks["completion"].finalize = _track_finalize

        await run_paper_pipeline(paper_id, pdf_path)

    assert call_order == [NODE_INGEST, NODE_CLASSIFY, NODE_EXTRACT, NODE_STORE]


async def test_run_paper_pipeline_extract_failure_short_circuits_store(
    integration_paper: tuple[str, Path],
) -> None:
    paper_id, pdf_path = integration_paper

    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["agent"].extract_graph = AsyncMock(
            side_effect=ServiceError("PIPELINE_FAILED", "extractor missing"),
        )
        await run_paper_pipeline(paper_id, pdf_path)
        mocks["store_save"].assert_not_called()

    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.FAILED
    assert status.failed_during == PipelineStage.EXTRACTING


async def test_run_paper_pipeline_rag_failure_still_reaches_ready(
    integration_paper: tuple[str, Path],
) -> None:
    """RAG indexing failure must promote to ready_with_warnings (not stuck indexing)."""

    paper_id, pdf_path = integration_paper

    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["rag_index"].side_effect = RuntimeError("embedding service unavailable")
        final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("failed") is not True
    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.READY_WITH_WARNINGS


async def test_run_paper_pipeline_rag_index_records_warning_on_failure(
    integration_paper: tuple[str, Path],
) -> None:
    """RAG indexing failure must be visible as extract_warnings."""

    from backend.rag.handlers import RAG_INDEX_WARNING_CODE

    paper_id, pdf_path = integration_paper

    with mock_pipeline_node_services(paper_id) as mocks:

        async def failing_rag_index(*_args: object, **_kwargs: object) -> None:
            from backend.repositories.pipeline_repository import PipelineRepository

            await PipelineRepository().record_warnings(paper_id, extract=[RAG_INDEX_WARNING_CODE])
            raise RuntimeError("embedding service unavailable")

        mocks["rag_index"].side_effect = failing_rag_index
        await run_paper_pipeline(paper_id, pdf_path)
        await drain_event_bus()

    paper = await get_paper_service().get_paper(paper_id)
    assert RAG_INDEX_WARNING_CODE in paper.extract_warnings


class FakeEmbeddingClient:
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 0.0] for text in texts]


async def test_run_paper_pipeline_builds_queryable_rag_index(
    integration_paper: tuple[str, Path],
    tmp_path: Path,
) -> None:
    """End-to-end: after pipeline success, the RAG vector index is queryable."""

    paper_id, pdf_path = integration_paper
    chroma_path = tmp_path / "chroma"
    rag_run_tracker = _InMemoryRagRunTracker()

    async def real_rag_index(*_args: object, **kwargs: object) -> None:
        from backend.rag.handlers import index_paper_for_rag

        store = VectorStore(
            embedding_client=FakeEmbeddingClient(),
            chroma_path=str(chroma_path),
            paper_service=rag_run_tracker,
        )
        full_text = kwargs["full_text"]
        await index_paper_for_rag(
            paper_id,
            full_text=full_text,
            graph=kwargs["graph"],
            vector_store=store,
            page_break_offsets=[len(full_text)],
        )

    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["ingest"].ingest = AsyncMock(
            return_value={
                "paper_id": paper_id,
                "full_text": "Methods\nWe propose a hybrid chunker.",
                "classifier_input": "classifier-input",
                "page_break_offsets": [len("Methods\nWe propose a hybrid chunker.")],
            },
        )
        mocks["rag_index"].side_effect = real_rag_index
        final = await run_paper_pipeline(paper_id, pdf_path)
        await drain_event_bus()

    assert final.get("failed") is not True
    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.READY

    # Directly query the produced vector store to prove indexing happened.
    store = VectorStore(
        embedding_client=FakeEmbeddingClient(),
        chroma_path=str(chroma_path),
        paper_service=rag_run_tracker,
    )
    results = await store.query_chunks("hybrid chunker", paper_id=paper_id, top_k=3)
    assert len(results) >= 1
    assert all(result.paper_id == paper_id for result in results)
    assert all(result.page_start is not None for result in results)
