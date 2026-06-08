"""Integration: LangGraph pipeline writes status/stage/percent per api-contract."""

from pathlib import Path
from unittest.mock import patch

import pytest
from backend.graph.state import STAGE_PERCENT
from backend.graph.workflow import run_paper_pipeline
from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage
from backend.services.paper_service import get_paper_service
from backend.services.pipeline_status_service import PipelineStatusService

from tests.helpers.status_contract import assert_snapshot_matches_contract


@pytest.fixture
def record_status_writes() -> list[PaperStatusData]:
    writes: list[PaperStatusData] = []
    original_apply = PipelineStatusService._apply

    def recording_apply(
        self: PipelineStatusService,
        paper_id: str,
        *,
        status: PaperStatus,
        stage: PipelineStage | None,
        percent: int,
        message: str,
    ) -> PaperStatusData:
        snapshot = original_apply(self, paper_id, status=status, stage=stage, percent=percent, message=message)
        writes.append(snapshot)
        return snapshot

    with patch.object(PipelineStatusService, "_apply", recording_apply):
        yield writes


async def test_successful_pipeline_emits_monotonic_processing_stages(
    workflow_paper: tuple[str, Path],
    mock_pipeline_dependencies: dict,
    record_status_writes: list[PaperStatusData],
) -> None:
    paper_id, pdf_path = workflow_paper
    await run_paper_pipeline(paper_id, pdf_path)

    processing_writes = [s for s in record_status_writes if s.status == PaperStatus.PROCESSING]
    stages_seen = [s.stage for s in processing_writes]
    assert PipelineStage.INGESTING in stages_seen
    assert PipelineStage.HEAD_REFINING in stages_seen
    assert PipelineStage.CLASSIFYING in stages_seen
    assert PipelineStage.EXTRACTING in stages_seen
    assert PipelineStage.STORING in stages_seen

    for snapshot in record_status_writes:
        assert_snapshot_matches_contract(snapshot)

    percents = [s.percent for s in processing_writes if s.stage is not None]
    assert percents == sorted(percents)


async def test_successful_pipeline_ends_with_ready_contract(
    workflow_paper: tuple[str, Path],
    mock_pipeline_dependencies: dict,
) -> None:
    paper_id, pdf_path = workflow_paper
    await run_paper_pipeline(paper_id, pdf_path)

    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.READY
    assert status.stage == PipelineStage.READY
    assert status.percent == STAGE_PERCENT[PipelineStage.READY]
    assert_snapshot_matches_contract(status)


async def test_failed_pipeline_ends_with_failed_contract(
    workflow_paper: tuple[str, Path],
    mock_pipeline_dependencies: dict,
) -> None:
    from unittest.mock import AsyncMock, MagicMock

    from backend.services.errors import ServiceError

    paper_id, pdf_path = workflow_paper
    ingest_svc = MagicMock()
    ingest_svc.ingest = AsyncMock(side_effect=ServiceError("INGEST_FAILED", "无法解析"))
    with patch("backend.graph.nodes.get_ingest_service", return_value=ingest_svc):
        await run_paper_pipeline(paper_id, pdf_path)

    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.FAILED
    assert status.stage == PipelineStage.FAILED
    assert status.percent == 0
    assert_snapshot_matches_contract(status)


async def test_start_processing_on_pipeline_launch(
    workflow_paper: tuple[str, Path],
    mock_pipeline_dependencies: dict,
    record_status_writes: list[PaperStatusData],
) -> None:
    paper_id, pdf_path = workflow_paper
    await run_paper_pipeline(paper_id, pdf_path)

    first = record_status_writes[0]
    assert first.status == PaperStatus.PROCESSING
    assert first.stage == PipelineStage.INGESTING
    assert first.percent == STAGE_PERCENT[PipelineStage.INGESTING]
