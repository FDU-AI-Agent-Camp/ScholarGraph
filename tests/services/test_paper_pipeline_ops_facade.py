# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""PaperService pipeline facade — LoD harden for RAG/watchdog callers."""

from __future__ import annotations

import pytest
from backend.services.paper_service import PaperService, get_paper_service


def test_paper_service_exposes_pipeline_facade_methods() -> None:
    service = get_paper_service()
    required = (
        "get_pipeline_snapshot",
        "save_pipeline_snapshot",
        "touch_indexing_heartbeat",
        "promote_paper_to_terminal_status",
        "promote_stuck_indexing_paper",
        "promote_stuck_indexing_paper_sync",
        "reset_pipeline_for_reextract",
        "list_stuck_indexing_papers",
        "list_stuck_indexing_paper_ids_sync",
    )
    for name in required:
        assert callable(getattr(service, name, None)), f"missing PaperService.{name}"


@pytest.mark.asyncio
async def test_promote_stuck_indexing_via_facade(persistence_env) -> None:
    from datetime import UTC, datetime, timedelta

    from backend.rag.indexing_watchdog import RAG_INDEXING_STUCK_WARNING, promote_stuck_indexing_paper
    from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage
    from backend.services.paper_service import get_paper_service as gps
    from tests.helpers.persistence_testkit import register_test_paper

    paper_id = "facade-stuck-001"
    await register_test_paper(paper_id, status=PaperStatus.INDEXING)
    service = gps()
    now = datetime.now(UTC)
    await service.save_pipeline_snapshot(
        paper_id,
        PaperStatusData(
            paper_id=paper_id,
            status=PaperStatus.INDEXING,
            percent=90,
            stage=PipelineStage.STORING,
            message="indexing",
            updated_at=now - timedelta(seconds=600),
            preview_available=False,
            error_code=None,
            failed_during=None,
            head_refine_warnings=[],
            classify_warnings=[],
            extract_warnings=[],
        ),
    )
    assert await promote_stuck_indexing_paper(paper_id) is True
    latest = await service.get_pipeline_snapshot(paper_id)
    assert latest is not None
    assert latest.status == PaperStatus.READY_WITH_WARNINGS
    assert RAG_INDEXING_STUCK_WARNING in latest.extract_warnings


def test_paper_service_composes_pipeline_ops_service() -> None:
    from backend.services.paper_pipeline_ops import PaperPipelineOpsService

    service = get_paper_service()
    assert isinstance(service, PaperService)
    assert isinstance(service._pipeline_ops, PaperPipelineOpsService)
