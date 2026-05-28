"""
端到端流水线集成测试（Mock BE-1～3，不调用真实 LLM / PDF 解析）。

对应 handoff：tests/integration/test_pipeline_mock.py
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.agents.workflow import run_paper_pipeline
from backend.graph.state import NODE_CLASSIFY, NODE_EXTRACT, NODE_INGEST, NODE_STORE, STAGE_PERCENT
from backend.graph.workflow import run_paper_pipeline as run_paper_pipeline_from_graph
from backend.schemas.graph import GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.errors import ServiceError
from backend.services.paper_service import get_paper_service

from tests.conftest import mock_pipeline_node_services
from tests.helpers.status_contract import assert_snapshot_matches_contract

pytestmark = pytest.mark.integration


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
            return classification

        async def track_extract(_text: str, _paradigm: Paradigm, *, paper_id: str):
            call_order.append(NODE_EXTRACT)
            return graph

        mocks["ingest"].ingest = AsyncMock(side_effect=track_ingest)
        mocks["agent"].classify_paradigm = AsyncMock(side_effect=track_classify)
        mocks["agent"].extract_graph = AsyncMock(side_effect=track_extract)
        mocks["store_save"].side_effect = lambda _g: call_order.append(NODE_STORE)

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
