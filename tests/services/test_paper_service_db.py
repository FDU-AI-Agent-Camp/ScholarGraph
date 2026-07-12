"""DB-backed PaperService unit tests."""

from __future__ import annotations

import pytest
from backend.schemas.paper import PaperStatus
from backend.services.paper_service import get_paper_service
from tests.helpers.persistence_testkit import register_test_paper, restart_paper_service

VALID_PDF = b"%PDF-1.4\n% service db test"


@pytest.mark.asyncio
async def test_create_from_upload_persists_pending_row(
    persistence_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("backend.services.paper_service.schedule_paper_pipeline", lambda *_a, **_k: None)
    service = await restart_paper_service()
    result = await service.create_from_upload(filename="svc.pdf", content=VALID_PDF)
    detail = await service.get_paper(result.paper_id)
    assert detail.status == PaperStatus.PENDING
    status = await service.get_status(result.paper_id)
    assert status.percent == 0


@pytest.mark.asyncio
async def test_set_status_snapshot_writes_pipeline_row(persistence_env) -> None:
    await register_test_paper("snap-001")
    service = await restart_paper_service()
    from backend.schemas.paper import PipelineStage
    from backend.services.pipeline_status_service import PipelineStatusService

    snapshot = PipelineStatusService().start_processing("snap-001")
    assert snapshot.status == PaperStatus.PROCESSING
    assert snapshot.stage == PipelineStage.INGESTING

    reloaded = await service.get_status("snap-001")
    assert reloaded.stage == PipelineStage.INGESTING


@pytest.mark.asyncio
async def test_record_warnings_visible_on_status(persistence_env) -> None:
    await register_test_paper("warn-svc")
    service = await restart_paper_service()
    service.record_classify_warnings("warn-svc", ["classifier_heuristic_fallback"])
    detail = await service.get_paper("warn-svc")
    assert detail.classify_warnings == ["classifier_heuristic_fallback"]
