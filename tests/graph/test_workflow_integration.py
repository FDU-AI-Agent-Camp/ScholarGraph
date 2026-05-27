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
from backend.services.paper_service import get_paper_service


async def test_pipeline_invokes_nodes_in_order(
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

    async def track_ingest(path: Path, paper_id: str | None = None):
        call_order.append(NODE_INGEST)
        return {
            "paper_id": paper_id or path.stem,
            "full_text": "full-text",
            "classifier_input": "classifier-input",
        }

    async def track_classify(_text: str):
        call_order.append(NODE_CLASSIFY)
        return classification

    async def track_extract(_text: str, _paradigm: Paradigm):
        call_order.append(NODE_EXTRACT)
        return graph

    mocks["ingest"].side_effect = track_ingest
    mocks["classify"].side_effect = track_classify
    mocks["extract"].side_effect = track_extract
    mocks["store_cls"].return_value.save = MagicMock(side_effect=lambda _g: call_order.append(NODE_STORE))

    await run_paper_pipeline(paper_id, pdf_path)

    assert call_order == [NODE_INGEST, NODE_CLASSIFY, NODE_EXTRACT, NODE_STORE]


async def test_pipeline_stops_at_classify_when_classify_fails(
    workflow_paper: tuple[str, Path],
    mock_pipeline_dependencies: dict,
) -> None:
    paper_id, pdf_path = workflow_paper
    mocks = mock_pipeline_dependencies
    mocks["classify"].side_effect = RuntimeError("schema mismatch")
    save_mock = MagicMock()
    mocks["store_cls"].return_value.save = save_mock

    final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("failed") is True
    assert final.get("error_code") == "LLM_JSON_INVALID"
    mocks["extract"].assert_not_awaited()
    save_mock.assert_not_called()

    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.FAILED
    assert status.stage == PipelineStage.FAILED


async def test_pipeline_stops_at_extract_when_extract_fails(
    workflow_paper: tuple[str, Path],
    mock_pipeline_dependencies: dict,
) -> None:
    paper_id, pdf_path = workflow_paper
    mocks = mock_pipeline_dependencies
    mocks["extract"].side_effect = NotImplementedError("extractor missing")
    save_mock = MagicMock()
    mocks["store_cls"].return_value.save = save_mock

    final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("failed") is True
    save_mock.assert_not_called()


async def test_pipeline_stops_at_store_when_save_fails(
    workflow_paper: tuple[str, Path],
    mock_pipeline_dependencies: dict,
) -> None:
    paper_id, pdf_path = workflow_paper
    mocks = mock_pipeline_dependencies
    mocks["store_cls"].return_value.save = MagicMock(side_effect=OSError("disk full"))

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
    assert exc_info.value.status_code == 404


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


async def test_pipeline_sets_processing_before_first_node(
    workflow_paper: tuple[str, Path],
    mock_pipeline_dependencies: dict,
) -> None:
    paper_id, pdf_path = workflow_paper
    observed: list[PaperStatus] = []
    service = get_paper_service()
    original_update = service.update_pipeline_status

    def spy_update(pid: str, **kwargs):
        observed.append(kwargs["status"])
        return original_update(pid, **kwargs)

    with patch.object(service, "update_pipeline_status", side_effect=spy_update):
        await run_paper_pipeline(paper_id, pdf_path)

    assert observed[0] == PaperStatus.PROCESSING


async def test_fail_path_after_ingest_error(
    workflow_paper: tuple[str, Path],
) -> None:
    paper_id, pdf_path = workflow_paper
    with patch("backend.graph.nodes.ingest_pdf", new_callable=AsyncMock) as ingest:
        ingest.side_effect = NotImplementedError("no ingest")
        final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("failed") is True
    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.FAILED
