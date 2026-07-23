# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Domain pipeline-ops tests: terminal promote + state-machine gating + RagIndexed fan-out."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from backend.events.bus import get_event_bus
from backend.events.types import RagIndexed
from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage
from backend.services.errors import InvalidStateTransitionError
from backend.services.paper_pipeline_ops import get_paper_pipeline_ops_service
from tests.helpers.persistence_testkit import register_test_paper


async def _seed_indexing(paper_id: str) -> None:
    await register_test_paper(paper_id, status=PaperStatus.INDEXING)
    ops = get_paper_pipeline_ops_service()
    await ops.heal_pipeline_snapshot(
        paper_id,
        PaperStatusData(
            paper_id=paper_id,
            status=PaperStatus.INDEXING,
            percent=85,
            stage=PipelineStage.STORING,
            message="indexing",
            updated_at=datetime.now(UTC),
            preview_available=False,
            error_code=None,
            failed_during=None,
            head_refine_warnings=[],
            classify_warnings=[],
            extract_warnings=[],
        ),
        reason="test_seed_indexing_for_promote",
    )


@pytest.mark.asyncio
async def test_promote_paper_to_terminal_status_publishes_rag_indexed(
    persistence_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paper_id = "domain-promote-ok"
    await _seed_indexing(paper_id)
    ops = get_paper_pipeline_ops_service()
    seen: list[RagIndexed] = []
    bus = get_event_bus()

    async def _capture(event: object) -> None:
        if isinstance(event, RagIndexed):
            persisted = await ops.get_pipeline_snapshot(paper_id)
            assert persisted is not None
            assert persisted.status == PaperStatus.READY
            seen.append(event)

    publish_spy = AsyncMock(side_effect=_capture)
    monkeypatch.setattr(bus, "publish", publish_spy)

    snapshot = await ops.promote_paper_to_terminal_status(
        paper_id,
        success=True,
        preferred_terminal=PaperStatus.READY,
    )
    assert snapshot.status == PaperStatus.READY
    latest = await ops.get_pipeline_snapshot(paper_id)
    assert latest is not None
    assert latest.status == PaperStatus.READY
    publish_spy.assert_awaited_once()
    assert len(seen) == 1
    assert seen[0].paper_id == paper_id
    assert seen[0].success is True
    assert seen[0].terminal_status == PaperStatus.READY


@pytest.mark.asyncio
async def test_promote_paper_to_terminal_status_failure_path_ready_with_warnings(
    persistence_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paper_id = "domain-promote-fail"
    await _seed_indexing(paper_id)
    ops = get_paper_pipeline_ops_service()
    seen: list[RagIndexed] = []
    bus = get_event_bus()

    async def _capture(event: object) -> None:
        if isinstance(event, RagIndexed):
            persisted = await ops.get_pipeline_snapshot(paper_id)
            assert persisted is not None
            assert persisted.status == PaperStatus.READY_WITH_WARNINGS
            seen.append(event)

    publish_spy = AsyncMock(side_effect=_capture)
    monkeypatch.setattr(bus, "publish", publish_spy)

    snapshot = await ops.promote_paper_to_terminal_status(
        paper_id,
        success=False,
        warning_codes=["rag_index_timeout"],
        message_override="index timed out",
    )
    assert snapshot.status == PaperStatus.READY_WITH_WARNINGS
    assert "rag_index_timeout" in snapshot.extract_warnings
    publish_spy.assert_awaited_once()
    assert seen and seen[0].success is False


@pytest.mark.asyncio
async def test_refuse_promote_from_ready_terminal_does_not_mutate_db(persistence_env) -> None:
    """Negative: ready → (promote again) must raise; DB snapshot must stay ready."""
    paper_id = "domain-promote-refuse"
    await _seed_indexing(paper_id)
    ops = get_paper_pipeline_ops_service()
    await ops.promote_paper_to_terminal_status(
        paper_id,
        success=True,
        preferred_terminal=PaperStatus.READY,
        publish_rag_indexed=False,
    )
    before = await ops.get_pipeline_snapshot(paper_id)
    assert before is not None
    assert before.status == PaperStatus.READY
    before_updated = before.updated_at

    with pytest.raises(InvalidStateTransitionError) as exc_info:
        await ops.promote_paper_to_terminal_status(
            paper_id,
            success=True,
            preferred_terminal=PaperStatus.READY,
        )
    assert exc_info.value.from_status == PaperStatus.READY.value
    assert exc_info.value.code == "INVALID_STATE_TRANSITION"

    after = await ops.get_pipeline_snapshot(paper_id)
    assert after is not None
    assert after.status == PaperStatus.READY
    assert after.updated_at == before_updated


@pytest.mark.asyncio
async def test_refuse_promote_when_not_indexing_pending(persistence_env) -> None:
    paper_id = "domain-promote-pending"
    await register_test_paper(paper_id, status=PaperStatus.PENDING)
    ops = get_paper_pipeline_ops_service()
    await ops.initialize_pipeline_snapshot(
        paper_id,
        PaperStatusData(
            paper_id=paper_id,
            status=PaperStatus.PENDING,
            percent=0,
            stage=None,
            message="queued",
            updated_at=datetime.now(UTC),
            preview_available=False,
            error_code=None,
            failed_during=None,
            head_refine_warnings=[],
            classify_warnings=[],
            extract_warnings=[],
        ),
    )
    with pytest.raises(InvalidStateTransitionError) as exc_info:
        await ops.promote_paper_to_terminal_status(paper_id, success=True)
    assert exc_info.value.from_status == PaperStatus.PENDING.value


def test_pipeline_repo_lod_script_is_clean() -> None:
    from scripts.check_pipeline_repo_lod import check_pipeline_repo_lod

    assert check_pipeline_repo_lod() == []
