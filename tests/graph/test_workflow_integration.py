"""Integration tests: compiled LangGraph pipeline end-to-end (mocked services)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.api.exceptions import ApiError
from backend.graph.state import NODE_CLASSIFY, NODE_EXTRACT, NODE_INGEST, NODE_STORE
from backend.graph.workflow import run_paper_pipeline
from backend.schemas.graph import GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.errors import ServiceError
from backend.services.paper_service import get_paper_service
from backend.services.pipeline_completion_service import PipelineCompletionService


async def test_pipeline_invokes_services_in_order(
    workflow_paper: tuple[str, Path],
    mock_pipeline_dependencies: dict,
) -> None:
    paper_id, pdf_path = workflow_paper
    call_order: list[str] = []
    classification = ParadigmClassification(
        paradigm=Paradigm.HSS,
        confidence=0.9,
        reason="mock",
    )
    graph = UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="N", type="Thesis")],
        edges=[],
    )

    mocks = mock_pipeline_dependencies

    async def track_ingest(path: Path, *, paper_id: str):
        call_order.append(NODE_INGEST)
        return {
            "paper_id": paper_id,
            "full_text": "full-text",
            "classifier_input": "classifier-input",
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


async def test_pipeline_stops_at_classify_when_classify_fails(
    workflow_paper: tuple[str, Path],
    mock_pipeline_dependencies: dict,
) -> None:
    paper_id, pdf_path = workflow_paper
    mocks = mock_pipeline_dependencies
    mocks["agent"].classify_paradigm = AsyncMock(
        side_effect=ServiceError("LLM_JSON_INVALID", "schema mismatch"),
    )

    final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("failed") is True
    assert final.get("error_code") == "LLM_JSON_INVALID"
    mocks["agent"].extract_graph.assert_not_awaited()
    mocks["store_save"].assert_not_called()

    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.FAILED


async def test_pipeline_stops_at_extract_when_extract_fails(
    workflow_paper: tuple[str, Path],
    mock_pipeline_dependencies: dict,
) -> None:
    paper_id, pdf_path = workflow_paper
    mocks = mock_pipeline_dependencies
    mocks["agent"].extract_graph = AsyncMock(
        side_effect=ServiceError("PIPELINE_FAILED", "extractor missing"),
    )

    final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("failed") is True
    mocks["store_save"].assert_not_called()


async def test_pipeline_stops_at_store_when_finalize_fails(
    workflow_paper: tuple[str, Path],
    mock_pipeline_dependencies: dict,
) -> None:
    paper_id, pdf_path = workflow_paper
    completion = PipelineCompletionService()
    with patch.object(
        completion,
        "finalize",
        side_effect=ServiceError("PIPELINE_FAILED", "disk full"),
    ):
        with patch(
            "backend.graph.nodes.get_pipeline_completion_service",
            return_value=completion,
        ):
            final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("failed") is True
    assert "disk full" in (final.get("error_message") or "")

    paper = await get_paper_service().get_paper(paper_id)
    assert paper.status == PaperStatus.FAILED


async def test_run_paper_pipeline_raises_when_pdf_missing(
    workflow_paper: tuple[str, Path],
) -> None:
    paper_id, _ = workflow_paper
    with pytest.raises(FileNotFoundError, match="PDF not found"):
        await run_paper_pipeline(paper_id, Path("/nonexistent/paper.pdf"))


async def test_run_paper_pipeline_raises_when_paper_not_registered(tmp_path: Path) -> None:
    pdf_path = tmp_path / "orphan.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    with pytest.raises(ApiError) as exc_info:
        await run_paper_pipeline("unknown-id", pdf_path)

    assert exc_info.value.code == "PAPER_NOT_FOUND"


async def test_pipeline_success_leaves_ready_status(
    workflow_paper: tuple[str, Path],
    mock_pipeline_dependencies: dict,
) -> None:
    paper_id, pdf_path = workflow_paper
    final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("status") == PaperStatus.READY
    status = await get_paper_service().get_status(paper_id)
    assert status.percent == 100
    assert status.stage == PipelineStage.READY

    graph = await get_paper_service().get_graph(paper_id)
    assert graph.paper_id == paper_id


async def test_fail_path_after_ingest_service_error(
    workflow_paper: tuple[str, Path],
) -> None:
    paper_id, pdf_path = workflow_paper
    ingest_svc = MagicMock()
    ingest_svc.ingest = AsyncMock(side_effect=ServiceError("PIPELINE_FAILED", "no ingest"))
    with patch("backend.graph.nodes.get_ingest_service", return_value=ingest_svc):
        final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("failed") is True
    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.FAILED
