# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""PaperPipelineOpsService — initialize / heal snapshot write contract."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import pytest
from backend.schemas.paper import PaperStatus, PaperStatusData
from backend.services.errors import InvalidStateTransitionError
from backend.services.paper_pipeline_ops import PaperPipelineOpsService, get_paper_pipeline_ops_service
from tests.helpers.persistence_testkit import register_test_paper

_OPS_LOGGER = "backend.services.paper_pipeline_ops"


def _pending_snapshot(paper_id: str, *, message: str = "queued") -> PaperStatusData:
    return PaperStatusData(
        paper_id=paper_id,
        status=PaperStatus.PENDING,
        percent=0,
        stage=None,
        message=message,
        updated_at=datetime.now(UTC),
    )


def _status_snapshot(
    paper_id: str,
    status: PaperStatus,
    *,
    message: str = "snapshot",
    percent: int = 100,
) -> PaperStatusData:
    return PaperStatusData(
        paper_id=paper_id,
        status=status,
        percent=percent,
        stage=None,
        message=message,
        updated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_initialize_snapshot_succeeds_with_pending(persistence_env) -> None:
    paper_id = "ops-init-pending-ok"
    await register_test_paper(paper_id, status=PaperStatus.PENDING, with_status_row=False)
    ops = get_paper_pipeline_ops_service()
    assert await ops.get_pipeline_snapshot(paper_id) is None

    await ops.initialize_pipeline_snapshot(paper_id, _pending_snapshot(paper_id, message="upload queued"))

    latest = await ops.get_pipeline_snapshot(paper_id)
    assert latest is not None
    assert latest.status == PaperStatus.PENDING
    assert latest.message == "upload queued"


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_status", [PaperStatus.READY, PaperStatus.INDEXING])
async def test_initialize_snapshot_raises_on_non_pending(
    persistence_env,
    bad_status: PaperStatus,
) -> None:
    paper_id = f"ops-init-reject-{bad_status.value}"
    await register_test_paper(paper_id, status=PaperStatus.PENDING)
    ops = get_paper_pipeline_ops_service()
    before = await ops.get_pipeline_snapshot(paper_id)
    assert before is not None
    assert before.status == PaperStatus.PENDING

    with pytest.raises(InvalidStateTransitionError) as exc_info:
        await ops.initialize_pipeline_snapshot(
            paper_id,
            _status_snapshot(paper_id, bad_status, message="illegal init"),
        )

    assert "non-PENDING" in str(exc_info.value)
    assert exc_info.value.to_status == bad_status.value
    after = await ops.get_pipeline_snapshot(paper_id)
    assert after is not None
    assert after.status == PaperStatus.PENDING
    assert after.message == before.message


@pytest.mark.asyncio
async def test_heal_snapshot_logs_audit_warning(
    persistence_env,
    caplog: pytest.LogCaptureFixture,
) -> None:
    paper_id = "ops-heal-audit"
    await register_test_paper(paper_id, status=PaperStatus.PENDING)
    ops = get_paper_pipeline_ops_service()
    healed = _status_snapshot(
        paper_id,
        PaperStatus.INDEXING,
        message="contract heal",
        percent=85,
    )

    with caplog.at_level(logging.WARNING, logger=_OPS_LOGGER):
        await ops.heal_pipeline_snapshot(
            paper_id,
            healed,
            reason="contract_drift_heal",
        )

    latest = await ops.get_pipeline_snapshot(paper_id)
    assert latest is not None
    assert latest.status == PaperStatus.INDEXING
    assert latest.message == "contract heal"

    audit_records = [record for record in caplog.records if record.getMessage() == "pipeline_snapshot_heal_applied"]
    assert len(audit_records) == 1
    audit = audit_records[0]
    assert audit.levelno == logging.WARNING
    assert getattr(audit, "paper_id", None) == paper_id
    assert getattr(audit, "heal_reason", None) == "contract_drift_heal"
    assert getattr(audit, "target_status", None) == PaperStatus.INDEXING.value


def test_save_snapshot_is_private() -> None:
    ops = get_paper_pipeline_ops_service()
    assert isinstance(ops, PaperPipelineOpsService)
    assert callable(getattr(ops, "_save_pipeline_snapshot", None))
    assert not hasattr(ops, "save_pipeline_snapshot")
    legacy_name = "save_pipeline_snapshot"
    with pytest.raises(AttributeError):
        getattr(ops, legacy_name)
