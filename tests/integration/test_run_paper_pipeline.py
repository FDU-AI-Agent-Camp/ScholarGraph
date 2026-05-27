"""run_paper_pipeline 功能与鲁棒性（async 入口、前置校验、终态）。"""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agents.workflow import run_paper_pipeline as run_from_agents
from backend.api.exceptions import ApiError
from backend.graph.workflow import get_compiled_paper_pipeline, run_paper_pipeline
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.services.errors import ServiceError
from backend.services.paper_service import get_paper_service
from backend.services.pipeline_status_service import get_pipeline_status_service
from tests.conftest import mock_pipeline_node_services

pytestmark = pytest.mark.integration


def test_run_paper_pipeline_is_async_callable() -> None:
    assert inspect.iscoroutinefunction(run_paper_pipeline)
    assert inspect.iscoroutinefunction(run_from_agents)


async def test_run_paper_pipeline_raises_file_not_found(integration_paper: tuple[str, Path]) -> None:
    paper_id, _ = integration_paper
    with pytest.raises(FileNotFoundError, match="PDF not found"):
        await run_paper_pipeline(paper_id, Path("/no/such/file.pdf"))


async def test_run_paper_pipeline_raises_when_paper_not_registered(tmp_path: Path) -> None:
    pdf_path = tmp_path / "orphan.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    with pytest.raises(ApiError) as exc_info:
        await run_paper_pipeline("unregistered-paper-id", pdf_path)
    assert exc_info.value.code == "PAPER_NOT_FOUND"


async def test_run_paper_pipeline_resolves_pdf_path(integration_paper: tuple[str, Path]) -> None:
    paper_id, pdf_path = integration_paper
    resolved_calls: list[Path] = []

    with mock_pipeline_node_services(paper_id) as mocks:

        async def capture_ingest(path: Path, *, paper_id: str):
            resolved_calls.append(path)
            return {
                "paper_id": paper_id,
                "full_text": "t",
                "classifier_input": "c",
            }

        mocks["ingest"].ingest.side_effect = capture_ingest
        await run_paper_pipeline(paper_id, pdf_path)

    assert resolved_calls[0].is_absolute()
    assert resolved_calls[0] == pdf_path.resolve()


async def test_run_paper_pipeline_calls_start_processing_before_graph(
    integration_paper: tuple[str, Path],
) -> None:
    paper_id, pdf_path = integration_paper
    events: list[str] = []

    original_start = get_pipeline_status_service().start_processing

    def track_start(pid: str, **kwargs):  # noqa: ANN003
        events.append("start_processing")
        return original_start(pid, **kwargs)

    compiled = get_compiled_paper_pipeline()

    async def track_ainvoke(initial):  # noqa: ANN001
        events.append("ainvoke")
        return {"failed": False, "status": PaperStatus.READY}

    with (
        patch.object(get_pipeline_status_service(), "start_processing", side_effect=track_start),
        patch.object(compiled, "ainvoke", side_effect=track_ainvoke),
        mock_pipeline_node_services(paper_id),
    ):
        await run_paper_pipeline(paper_id, pdf_path)

    assert events == ["start_processing", "ainvoke"]


async def test_run_paper_pipeline_success_final_state_fields(
    integration_paper: tuple[str, Path],
) -> None:
    paper_id, pdf_path = integration_paper
    with mock_pipeline_node_services(paper_id):
        final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("failed") is not True
    assert final.get("status") == PaperStatus.READY
    assert final.get("stage") == PipelineStage.READY


async def test_run_paper_pipeline_failure_final_state_fields(
    integration_paper: tuple[str, Path],
) -> None:
    paper_id, pdf_path = integration_paper
    ingest_svc = MagicMock()
    ingest_svc.ingest = AsyncMock(
        side_effect=ServiceError("INGEST_FAILED", "损坏的 PDF"),
    )
    with patch("backend.graph.nodes.get_ingest_service", return_value=ingest_svc):
        final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("failed") is True
    assert final.get("error_code") == "INGEST_FAILED"
    assert final.get("error_message") == "损坏的 PDF"
    assert final.get("failed_during") == PipelineStage.INGESTING


async def test_run_paper_pipeline_classify_failure_does_not_reach_store(
    integration_paper: tuple[str, Path],
) -> None:
    paper_id, pdf_path = integration_paper
    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["agent"].classify_paradigm = AsyncMock(
            side_effect=ServiceError("LLM_JSON_INVALID", "bad"),
        )
        await run_paper_pipeline(paper_id, pdf_path)
        mocks["store_save"].assert_not_called()


async def test_run_paper_pipeline_second_run_after_failure_can_succeed(
    integration_paper: tuple[str, Path],
) -> None:
    """失败后再次执行（Mock 成功）可恢复为 ready — 验证状态可被覆盖写入。"""
    paper_id, pdf_path = integration_paper
    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["ingest"].ingest = AsyncMock(side_effect=ServiceError("INGEST_FAILED", "首次失败"))
        first = await run_paper_pipeline(paper_id, pdf_path)
    assert first.get("failed") is True

    with mock_pipeline_node_services(paper_id):
        second = await run_paper_pipeline(paper_id, pdf_path)

    assert second.get("failed") is not True
    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.READY
