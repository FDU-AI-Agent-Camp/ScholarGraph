"""Shared assertions for api-contract §2 status/stage/percent rules."""

from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage
from backend.services.pipeline_status_service import validate_status_contract


def assert_status_contract(
    *,
    status: PaperStatus,
    stage: PipelineStage | None,
    percent: int,
) -> None:
    validate_status_contract(status=status, stage=stage, percent=percent)


def assert_snapshot_matches_contract(snapshot: PaperStatusData) -> None:
    assert_status_contract(
        status=snapshot.status,
        stage=snapshot.stage,
        percent=snapshot.percent,
    )
