"""Problem 2 (processing): Watchdog commit survives main asyncio loop starvation.

Injects bare ``time.sleep`` on the event-loop thread and asserts the dedicated
OS-thread processing watchdog still fails a stale PROCESSING paper via sync SQL.
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
from backend.db.models import PaperRow, PipelineRunRow
from backend.graph.state import STAGE_PERCENT
from backend.pipeline.processing_watchdog import (
    PROCESS_TIMEOUT_CODE,
    PROCESS_WATCHDOG_HEAL_TAG,
    PROCESSING_WATCHDOG_TICK_LOG,
    clear_processing_watchdog_tick_timestamps,
    processing_watchdog_tick_monotonic_timestamps,
    reset_processing_watchdog_sync_engine,
    start_processing_watchdog,
    stop_processing_watchdog,
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

PAPER_P = "paper-processing-starve"
WATCHDOG_INTERVAL_SECONDS = 1.0
STUCK_AFTER_SECONDS = 2.0
PENDING_QUEUE_TIMEOUT_SECONDS = 3600.0
MAIN_LOOP_BLOCK_SECONDS = 5.0
PROBE_AT_SECONDS = 3.0
MIN_TICKS_DURING_BLOCK = 3


@pytest.fixture
def processing_starvation_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "processing-watchdog-starvation.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("SCHOLARGRAPH_IGNORE_DOTENV", "1")
    monkeypatch.setenv("PROCESS_WATCHDOG_ENABLED", "true")
    monkeypatch.setenv("PROCESS_WATCHDOG_INTERVAL_SECONDS", str(WATCHDOG_INTERVAL_SECONDS))
    monkeypatch.setenv("PROCESS_WATCHDOG_SECONDS", str(STUCK_AFTER_SECONDS))
    monkeypatch.setenv("PENDING_QUEUE_TIMEOUT_SECONDS", str(PENDING_QUEUE_TIMEOUT_SECONDS))
    monkeypatch.setenv("PROCESS_ORPHAN_GRACE_SECONDS", "10")
    get_settings.cache_clear()
    reset_persistence_singletons()
    reset_processing_watchdog_sync_engine()
    clear_processing_watchdog_tick_timestamps()
    stop_processing_watchdog()
    run_async(init_isolated_database(db_path))
    yield db_path
    stop_processing_watchdog()
    register_main_event_loop(None)
    reset_processing_watchdog_sync_engine()
    reset_persistence_singletons()
    get_settings.cache_clear()


async def _put_paper_processing_stale(paper_id: str, *, updated_at: datetime) -> None:
    await register_test_paper(paper_id, status=PaperStatus.PENDING, with_status_row=True)
    snapshot = PaperStatusData(
        paper_id=paper_id,
        status=PaperStatus.PROCESSING,
        percent=STAGE_PERCENT[PipelineStage.EXTRACTING],
        stage=PipelineStage.EXTRACTING,
        message="processing",
        updated_at=datetime.now(UTC),
    )
    await get_pipeline_repository().save_status(paper_id, snapshot)
    async with get_async_session_factory()() as session:
        run = await session.get(PipelineRunRow, paper_id)
        paper = await session.get(PaperRow, paper_id)
        assert run is not None and paper is not None
        run.updated_at = updated_at
        paper.updated_at = updated_at
        paper.status = PaperStatus.PROCESSING.value
        await session.commit()


def _sync_read_paper_status_and_code(database_url: str, paper_id: str) -> tuple[str | None, str | None]:
    engine = create_engine(database_url, future=True)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    try:
        with factory() as session:
            paper = session.get(PaperRow, paper_id)
            run = session.get(PipelineRunRow, paper_id)
            status = None if paper is None else paper.status
            code = None if run is None else run.error_code
            return status, code
    finally:
        engine.dispose()


@pytest.mark.asyncio
@pytest.mark.process_release_gate
async def test_processing_watchdog_loop_starvation(
    processing_starvation_db: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """主 loop ``time.sleep`` 硬阻塞期间 processing watchdog 仍独立 tick + fail。"""
    caplog.set_level(logging.INFO)

    stale = datetime.now(UTC) - timedelta(seconds=STUCK_AFTER_SECONDS)
    await _put_paper_processing_stale(PAPER_P, updated_at=stale)

    register_main_event_loop(asyncio.get_running_loop())
    clear_processing_watchdog_tick_timestamps()
    stop_processing_watchdog()
    start_processing_watchdog()

    database_url = get_settings().database_url
    probe_state: dict[str, str | None] = {"status": None, "error_code": None}
    probe_error: list[BaseException] = []

    def _probe_during_starvation() -> None:
        try:
            time.sleep(PROBE_AT_SECONDS)
            status, code = _sync_read_paper_status_and_code(database_url, PAPER_P)
            probe_state["status"] = status
            probe_state["error_code"] = code
        except BaseException as exc:  # noqa: BLE001 — surface into parent assertions
            probe_error.append(exc)

    probe = threading.Thread(target=_probe_during_starvation, name="processing-starve-probe", daemon=True)
    probe.start()

    block_started = time.monotonic()
    time.sleep(MAIN_LOOP_BLOCK_SECONDS)
    block_ended = time.monotonic()

    probe.join(timeout=2.0)
    stop_processing_watchdog()
    register_main_event_loop(None)

    assert not probe_error, f"probe failed: {probe_error!r}"

    ticks = [ts for ts in processing_watchdog_tick_monotonic_timestamps() if block_started <= ts <= block_ended]
    assert len(ticks) >= MIN_TICKS_DURING_BLOCK, (
        f"expected ≥{MIN_TICKS_DURING_BLOCK} ticks during main-loop block, got {len(ticks)}: {ticks}"
    )
    if len(ticks) >= 2:
        gaps = [ticks[i + 1] - ticks[i] for i in range(len(ticks) - 1)]
        assert min(gaps) >= 0.2
        assert max(gaps) <= WATCHDOG_INTERVAL_SECONDS + 1.5

    tick_logs = [r for r in caplog.records if r.getMessage() == PROCESSING_WATCHDOG_TICK_LOG]
    assert len(tick_logs) >= MIN_TICKS_DURING_BLOCK

    assert probe_state["status"] == PaperStatus.FAILED.value
    assert probe_state["error_code"] == PROCESS_TIMEOUT_CODE
    assert any(PROCESS_WATCHDOG_HEAL_TAG in r.getMessage() for r in caplog.records)

    final_status, final_code = _sync_read_paper_status_and_code(database_url, PAPER_P)
    assert final_status == PaperStatus.FAILED.value
    assert final_code == PROCESS_TIMEOUT_CODE
