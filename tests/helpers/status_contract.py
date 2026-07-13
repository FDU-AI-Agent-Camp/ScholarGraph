"""Shared assertions for api-contract §2 status/stage/percent rules."""

from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage
from backend.services.pipeline_status_service import (
    validate_failed_error_fields,
    validate_status_contract,
)


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
    validate_failed_error_fields(
        status=snapshot.status,
        error_code=snapshot.error_code,
        failed_during=snapshot.failed_during,
    )


def assert_terminal_ready_envelope(data: dict) -> None:
    """HTTP status payload must satisfy api-contract terminal ready triple."""
    assert data["status"] == "ready"
    # ScholarGraph api-contract uses stage=ready (not "completed") at 100%.
    assert data["stage"] == "ready"
    assert data["percent"] == 100


def assert_terminal_failed_envelope(data: dict) -> None:
    """HTTP status payload must satisfy api-contract terminal failed triple."""
    assert data["status"] == "failed"
    assert data["stage"] == "failed"
    assert data.get("error_code")
