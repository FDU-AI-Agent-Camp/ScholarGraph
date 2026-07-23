# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""DB-backed PaperService unit tests."""

from __future__ import annotations

import pytest
from backend.schemas.paper import PaperStatus
from backend.services.paper_warning_service import WarningType, get_paper_warning_service
from tests.helpers.persistence_testkit import register_test_paper, restart_paper_service

VALID_PDF = b"%PDF-1.4\n% service db test"


@pytest.mark.asyncio
async def test_create_from_upload_persists_pending_row(
    persistence_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import AsyncMock

    from backend.services.paper_pipeline_ops import get_paper_pipeline_ops_service
    from backend.services.paper_service import UPLOAD_QUEUED_MESSAGE

    monkeypatch.setattr("backend.services.paper_service.schedule_paper_pipeline", lambda *_a, **_k: None)
    service = await restart_paper_service()
    real_initialize = service._pipeline_ops.initialize_pipeline_snapshot
    initialize_spy = AsyncMock(side_effect=real_initialize)
    monkeypatch.setattr(service._pipeline_ops, "initialize_pipeline_snapshot", initialize_spy)

    result = await service.create_from_upload(filename="svc.pdf", content=VALID_PDF)

    detail = await service.get_paper(result.paper_id)
    assert detail.status == PaperStatus.PENDING
    status = await service.get_status(result.paper_id)
    assert status.status == PaperStatus.PENDING
    assert status.percent == 0
    assert status.message == UPLOAD_QUEUED_MESSAGE

    initialize_spy.assert_awaited_once()
    init_snapshot = initialize_spy.await_args.args[1]
    assert init_snapshot.status == PaperStatus.PENDING
    assert init_snapshot.message == UPLOAD_QUEUED_MESSAGE

    ops = get_paper_pipeline_ops_service()
    persisted = await ops.get_pipeline_snapshot(result.paper_id)
    assert persisted is not None
    assert persisted.status == PaperStatus.PENDING
    assert persisted.percent == 0
    assert persisted.message == UPLOAD_QUEUED_MESSAGE


@pytest.mark.asyncio
async def test_set_status_snapshot_writes_pipeline_row(persistence_env) -> None:
    await register_test_paper("snap-001")
    service = await restart_paper_service()
    from backend.schemas.paper import PipelineStage
    from backend.services.pipeline_status_service import PipelineStatusService

    snapshot = await PipelineStatusService().start_processing("snap-001")
    assert snapshot.status == PaperStatus.PROCESSING
    assert snapshot.stage == PipelineStage.INGESTING

    reloaded = await service.get_status("snap-001")
    assert reloaded.stage == PipelineStage.INGESTING


@pytest.mark.asyncio
async def test_record_warnings_visible_on_status(persistence_env) -> None:
    await register_test_paper("warn-svc")
    service = await restart_paper_service()
    await get_paper_warning_service().record("warn-svc", WarningType.CLASSIFY, ["classifier_heuristic_fallback"])
    detail = await service.get_paper("warn-svc")
    assert detail.classify_warnings == ["classifier_heuristic_fallback"]
