# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""P13 anti-regression CI gates — timeout audit + heal log marker."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest
from backend.config import get_settings
from backend.graph.state import STAGE_PERCENT
from backend.rag.indexing_watchdog import (
    P13_WATCHDOG_HEAL_TAG,
    RAG_INDEXING_STUCK_WARNING,
    promote_stuck_indexing_paper,
)
from backend.repositories.async_bridge import run_async
from backend.repositories.pipeline_repository import get_pipeline_repository
from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage

from tests.helpers.persistence_testkit import (
    init_isolated_database,
    register_test_paper,
    reset_persistence_singletons,
)


def test_static_rag_io_timeout_audit_passes() -> None:
    from scripts.check_rag_io_timeouts import run_all_checks

    errors = run_all_checks()
    assert errors == [], "RAG I/O timeout audit regressions:\n" + "\n".join(errors)


@pytest.mark.asyncio
async def test_watchdog_heal_log_contains_ops_alert_tag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    db_path = tmp_path / "p13-log.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("SCHOLARGRAPH_IGNORE_DOTENV", "1")
    get_settings.cache_clear()
    reset_persistence_singletons()
    run_async(init_isolated_database(db_path))

    async def _seed() -> None:
        await register_test_paper("heal-log-1", status=PaperStatus.PENDING, with_status_row=True)
        await get_pipeline_repository().save_status(
            "heal-log-1",
            PaperStatusData(
                paper_id="heal-log-1",
                status=PaperStatus.INDEXING,
                percent=STAGE_PERCENT[PipelineStage.INDEXING],
                stage=PipelineStage.INDEXING,
                message="indexing",
                updated_at=datetime.now(UTC),
            ),
        )

    run_async(_seed())

    with caplog.at_level(logging.WARNING, logger="backend.rag.indexing_watchdog"):
        promoted = run_async(promote_stuck_indexing_paper("heal-log-1"))

    assert promoted is True
    assert any(P13_WATCHDOG_HEAL_TAG in record.getMessage() for record in caplog.records)
    assert any("indexing_watchdog_promoted" in record.getMessage() for record in caplog.records)

    latest = run_async(get_pipeline_repository().get_latest("heal-log-1"))
    assert latest is not None
    assert RAG_INDEXING_STUCK_WARNING in latest.extract_warnings

    reset_persistence_singletons()
    get_settings.cache_clear()
