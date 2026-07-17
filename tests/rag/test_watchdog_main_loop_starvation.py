# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Problem 2 verification: Watchdog keeps ticking while the main asyncio loop is starved.

Injects a bare ``time.sleep`` on the pytest/FastAPI event-loop thread (false-async)
and asserts the dedicated monitor thread still scans and promotes stuck INDEXING.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from backend.config import get_settings
from backend.db.base import get_async_session_factory
from backend.db.models import PipelineRunRow
from backend.graph.state import STAGE_PERCENT
from backend.rag.indexing_watchdog import (
    INDEXING_WATCHDOG_TICK_LOG,
    P13_WATCHDOG_HEAL_TAG,
    RAG_INDEXING_STUCK_WARNING,
    clear_watchdog_tick_timestamps,
    reset_watchdog_sync_engine,
    start_indexing_watchdog,
    stop_indexing_watchdog,
    watchdog_tick_monotonic_timestamps,
)
from backend.repositories.async_bridge import register_main_event_loop, run_async
from backend.repositories.pipeline_repository import get_pipeline_repository
from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from tests.helpers.persistence_testkit import (
    init_isolated_database,
    register_test_paper,
    reset_persistence_singletons,
)

PAPER_Y = "paper-y"
WATCHDOG_INTERVAL_SECONDS = 1.0
STUCK_AFTER_SECONDS = 2.0
HEARTBEAT_STALE_SECONDS = 1.5
MAIN_LOOP_BLOCK_SECONDS = 5.0
PROBE_AT_SECONDS = 3.0
MIN_TICKS_DURING_BLOCK = 3


@pytest.fixture
def starvation_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "watchdog-starvation.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("SCHOLARGRAPH_IGNORE_DOTENV", "1")
    monkeypatch.setenv("RAG_INDEXING_WATCHDOG_ENABLED", "true")
    monkeypatch.setenv("RAG_INDEXING_WATCHDOG_INTERVAL_SECONDS", str(WATCHDOG_INTERVAL_SECONDS))
    monkeypatch.setenv("RAG_INDEXING_WATCHDOG_SECONDS", str(STUCK_AFTER_SECONDS))
    monkeypatch.setenv("RAG_INDEXING_HEARTBEAT_STALE_SECONDS", str(HEARTBEAT_STALE_SECONDS))
    get_settings.cache_clear()
    reset_persistence_singletons()
    reset_watchdog_sync_engine()
    clear_watchdog_tick_timestamps()
    stop_indexing_watchdog()
    run_async(init_isolated_database(db_path))
    yield db_path
    stop_indexing_watchdog()
    register_main_event_loop(None)
    reset_watchdog_sync_engine()
    reset_persistence_singletons()
    get_settings.cache_clear()


async def _put_paper_indexing(
    paper_id: str,
    *,
    started_at: datetime,
    heartbeat_at: datetime | None = None,
) -> None:
    await register_test_paper(paper_id, status=PaperStatus.PENDING, with_status_row=True)
    snapshot = PaperStatusData(
        paper_id=paper_id,
        status=PaperStatus.INDEXING,
        percent=STAGE_PERCENT[PipelineStage.INDEXING],
        stage=PipelineStage.INDEXING,
        message="indexing",
        updated_at=datetime.now(UTC),
        extract_warnings=[],
    )
    await get_pipeline_repository().save_status(paper_id, snapshot)
    pulse = heartbeat_at if heartbeat_at is not None else started_at
    async with get_async_session_factory()() as session:
        run = await session.get(PipelineRunRow, paper_id)
        assert run is not None
        run.indexing_started_at = started_at
        run.indexing_heartbeat = pulse
        run.updated_at = pulse
        await session.commit()


def _sync_read_paper_status(database_url: str, paper_id: str) -> str | None:
    """Read paper status via sync SQLAlchemy (does not need the main asyncio loop)."""
    engine = create_engine(database_url, future=True)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    try:
        with factory() as session:
            from backend.db.models import PaperRow

            row = session.get(PaperRow, paper_id)
            return None if row is None else row.status
    finally:
        engine.dispose()


@pytest.mark.asyncio
@pytest.mark.p13_release_gate
async def test_watchdog_works_during_event_loop_starvation(
    starvation_db: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """隔离监控：主 loop ``time.sleep`` 硬阻塞期间 Watchdog 仍独立 tick + promote."""
    caplog.set_level(logging.INFO)

    # Paper Y already past stuck + heartbeat-stale thresholds before the block.
    started = datetime.now(UTC) - timedelta(seconds=STUCK_AFTER_SECONDS)
    await _put_paper_indexing(PAPER_Y, started_at=started, heartbeat_at=started)

    # Production-shaped affinity: worker ``run_async`` would otherwise target this loop.
    register_main_event_loop(asyncio.get_running_loop())
    clear_watchdog_tick_timestamps()
    stop_indexing_watchdog()
    start_indexing_watchdog()

    database_url = get_settings().database_url
    status_at_probe: dict[str, str | None] = {"status": None}
    probe_error: list[BaseException] = []

    def _probe_during_starvation() -> None:
        try:
            time.sleep(PROBE_AT_SECONDS)
            status_at_probe["status"] = _sync_read_paper_status(database_url, PAPER_Y)
        except BaseException as exc:  # noqa: BLE001 — surface into parent assertions
            probe_error.append(exc)

    probe = threading.Thread(target=_probe_during_starvation, name="starvation-probe", daemon=True)
    probe.start()

    block_started = time.monotonic()
    # Bare sync sleep on the asyncio loop thread — the false-async failure mode.
    time.sleep(MAIN_LOOP_BLOCK_SECONDS)
    block_ended = time.monotonic()

    probe.join(timeout=2.0)
    stop_indexing_watchdog()
    register_main_event_loop(None)

    assert not probe_error, f"probe failed: {probe_error!r}"

    ticks = [ts for ts in watchdog_tick_monotonic_timestamps() if block_started <= ts <= block_ended]
    # Invariant 1 — clock decoupling: ≥3 ticks while main loop was occupied (~1s interval).
    assert len(ticks) >= MIN_TICKS_DURING_BLOCK, (
        f"expected ≥{MIN_TICKS_DURING_BLOCK} watchdog ticks during main-loop block, got {len(ticks)}: {ticks}"
    )
    if len(ticks) >= 2:
        gaps = [ticks[i + 1] - ticks[i] for i in range(len(ticks) - 1)]
        # Allow scheduler jitter; gaps should cluster near the configured interval.
        assert min(gaps) >= 0.2
        assert max(gaps) <= WATCHDOG_INTERVAL_SECONDS + 1.5

    tick_logs = [r for r in caplog.records if r.getMessage() == INDEXING_WATCHDOG_TICK_LOG]
    assert len(tick_logs) >= MIN_TICKS_DURING_BLOCK

    # Invariant 2 — forced heal by ~3s into the block (observer thread sync read).
    assert status_at_probe["status"] == PaperStatus.READY_WITH_WARNINGS.value

    # Invariant 3 — heartbeat-stale stuck path emitted the ops heal marker.
    assert any(P13_WATCHDOG_HEAL_TAG in r.getMessage() for r in caplog.records)
    assert any(
        RAG_INDEXING_STUCK_WARNING in r.getMessage() or "indexing_watchdog_promoted" in r.getMessage()
        for r in caplog.records
    )

    # Final consistency via sync read (main loop still may be flaky after sleep).
    final_status = _sync_read_paper_status(database_url, PAPER_Y)
    assert final_status == PaperStatus.READY_WITH_WARNINGS.value
