# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Domain state machine — exercises production PipelineStatusService + contracts.

False-test avoidance: illegal transitions are asserted through ``start_processing`` /
``mark_*`` (which call ``_apply`` → ``assert_status_transition_allowed``), not by
calling the ADT helper in isolation.
"""

from __future__ import annotations

import pytest
from backend.graph.state import STAGE_PERCENT
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.services.errors import InvalidStateTransitionError
from backend.services.paper_pipeline_ops import get_paper_pipeline_ops_service
from backend.services.paper_service import get_paper_service
from backend.services.pipeline_status_service import (
    PROCESSING_STAGES,
    PipelineStatusService,
    validate_failed_error_fields,
    validate_status_contract,
)
from tests.helpers.persistence_testkit import register_test_paper
from tests.helpers.status_contract import assert_snapshot_matches_contract


def _legal_triples() -> list[tuple[PaperStatus, PipelineStage | None, int]]:
    rows: list[tuple[PaperStatus, PipelineStage | None, int]] = [
        (PaperStatus.PENDING, None, 0),
        (PaperStatus.INDEXING, PipelineStage.INDEXING, STAGE_PERCENT[PipelineStage.INDEXING]),
        (PaperStatus.READY, PipelineStage.READY, 100),
        (PaperStatus.READY_WITH_WARNINGS, PipelineStage.READY, 100),
        (PaperStatus.FAILED, PipelineStage.FAILED, 0),
    ]
    for stage in PROCESSING_STAGES:
        rows.append((PaperStatus.PROCESSING, stage, STAGE_PERCENT[stage]))
    return rows


@pytest.mark.parametrize(("status", "stage", "percent"), _legal_triples())
def test_production_status_contract_accepts_every_legal_triple(
    status: PaperStatus,
    stage: PipelineStage | None,
    percent: int,
) -> None:
    """Pure contract fn used by every pipeline write — must accept the ADT surface."""
    validate_status_contract(status=status, stage=stage, percent=percent)
    if status == PaperStatus.FAILED:
        validate_failed_error_fields(
            status=status,
            error_code="PIPELINE_FAILED",
            failed_during=PipelineStage.EXTRACTING,
        )
    else:
        validate_failed_error_fields(status=status, error_code=None, failed_during=None)


@pytest.mark.parametrize("status", list(PaperStatus))
def test_every_paper_status_enum_member_has_legal_contract_row(status: PaperStatus) -> None:
    assert any(row[0] == status for row in _legal_triples()), status


@pytest.mark.asyncio
async def test_fail_from_processing_invariant_leaves_failed_with_error_code(
    persistence_env,
) -> None:
    """Production ``mark_failed``: never stuck in processing; error_code persisted."""
    paper_id = "inv-fail-processing"
    await register_test_paper(paper_id, status=PaperStatus.PENDING)
    svc = PipelineStatusService()
    await svc.start_processing(paper_id)
    await svc.advance_stage(paper_id, PipelineStage.EXTRACTING)

    failed = await svc.mark_failed(
        paper_id,
        message="extract boom",
        error_code="LLM_JSON_INVALID",
        failed_during=PipelineStage.EXTRACTING,
    )
    assert_snapshot_matches_contract(failed)
    assert failed.status == PaperStatus.FAILED
    assert failed.error_code == "LLM_JSON_INVALID"
    assert failed.failed_during is not None

    paper = await get_paper_service().get_paper(paper_id)
    assert paper.status == PaperStatus.FAILED
    latest = await get_paper_pipeline_ops_service().get_pipeline_snapshot(paper_id)
    assert latest is not None
    assert latest.status == PaperStatus.FAILED
    assert latest.error_code == "LLM_JSON_INVALID"


@pytest.mark.asyncio
async def test_negative_ready_to_indexing_via_mark_indexing(persistence_env) -> None:
    """Production gate: READY → INDEXING via ``mark_indexing`` must not dirty-write."""
    paper_id = "neg-ready-idx"
    await register_test_paper(paper_id, status=PaperStatus.PENDING)
    svc = PipelineStatusService()
    await svc.mark_ready(paper_id)
    before = await get_paper_pipeline_ops_service().get_pipeline_snapshot(paper_id)
    assert before is not None
    before_updated = before.updated_at

    with pytest.raises(InvalidStateTransitionError) as exc_info:
        await svc.mark_indexing(paper_id)

    assert exc_info.value.from_status == PaperStatus.READY.value
    assert exc_info.value.to_status == PaperStatus.INDEXING.value

    after = await get_paper_pipeline_ops_service().get_pipeline_snapshot(paper_id)
    assert after is not None
    assert after.status == PaperStatus.READY
    assert after.updated_at == before_updated


@pytest.mark.asyncio
async def test_negative_indexing_to_processing_via_advance_stage(persistence_env) -> None:
    """Production gate: INDEXING cannot reverse into PROCESSING stage advances."""
    paper_id = "neg-idx-proc"
    await register_test_paper(paper_id, status=PaperStatus.PENDING)
    svc = PipelineStatusService()
    await svc.start_processing(paper_id)
    await svc.mark_indexing(paper_id)
    before = await get_paper_pipeline_ops_service().get_pipeline_snapshot(paper_id)
    assert before is not None
    assert before.status == PaperStatus.INDEXING
    before_updated = before.updated_at

    with pytest.raises(InvalidStateTransitionError) as exc_info:
        await svc.advance_stage(paper_id, PipelineStage.EXTRACTING)

    assert exc_info.value.from_status == PaperStatus.INDEXING.value
    assert exc_info.value.to_status == PaperStatus.PROCESSING.value

    after = await get_paper_pipeline_ops_service().get_pipeline_snapshot(paper_id)
    assert after is not None
    assert after.status == PaperStatus.INDEXING
    assert after.updated_at == before_updated


@pytest.mark.asyncio
async def test_ready_to_processing_reentry_is_allowed(persistence_env) -> None:
    """``run_paper_pipeline`` may re-enter PROCESSING from READY without requeue."""
    paper_id = "ok-ready-proc"
    await register_test_paper(paper_id, status=PaperStatus.PENDING)
    svc = PipelineStatusService()
    await svc.mark_ready(paper_id)
    snapshot = await svc.start_processing(paper_id)
    assert snapshot.status == PaperStatus.PROCESSING
    paper = await get_paper_service().get_paper(paper_id)
    assert paper.status == PaperStatus.PROCESSING


@pytest.mark.asyncio
async def test_failed_to_failed_idempotent_backfill_is_allowed(persistence_env) -> None:
    """``mark_failed`` while already FAILED must be able to backfill error fields."""
    paper_id = "ok-fail-fail"
    await register_test_paper(paper_id, status=PaperStatus.PENDING)
    svc = PipelineStatusService()
    await svc.start_processing(paper_id)
    await svc.mark_failed(
        paper_id,
        message="first",
        error_code="PIPELINE_FAILED",
        failed_during=PipelineStage.INGESTING,
    )
    second = await svc.mark_failed(
        paper_id,
        message="backfill",
        error_code="INGEST_FAILED",
        failed_during=PipelineStage.INGESTING,
    )
    assert second.status == PaperStatus.FAILED
    assert second.error_code == "INGEST_FAILED"
    assert second.message == "backfill"
