"""Problem 2 (processing): Watchdog commit survives main asyncio loop starvation.

Release-gate hard stop (``make process-release-gate`` / ``make ci-patrol-release``):
inject bare ``time.sleep`` on the event-loop thread and assert the dedicated OS-thread
processing watchdog still fails a zombie that was planted **during** the starvation
window via sync SQL (physically isolated from the starved FastAPI / asyncio pump).
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
from backend.db.models import PaperRow, PipelineRunRow
from backend.graph.state import STAGE_PERCENT
from backend.pipeline.processing_watchdog import (
    PROCESS_TIMEOUT_CODE,
    PROCESS_WATCHDOG_HEAL_TAG,
    PROCESSING_WATCHDOG_THREAD_NAME,
    PROCESSING_WATCHDOG_TICK_LOG,
    clear_processing_watchdog_tick_timestamps,
    processing_watchdog_thread_is_alive,
    processing_watchdog_tick_monotonic_timestamps,
    reset_processing_watchdog_sync_engine,
    start_processing_watchdog,
    stop_processing_watchdog,
)
from backend.repositories.async_bridge import register_main_event_loop, run_async
from backend.schemas.paper import PaperStatus, PipelineStage
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from tests.helpers.persistence_testkit import init_isolated_database, reset_persistence_singletons

PAPER_P = "paper-processing-starve"
WATCHDOG_INTERVAL_SECONDS = 1.0
STUCK_AFTER_SECONDS = 2.0
PENDING_QUEUE_TIMEOUT_SECONDS = 3600.0
MAIN_LOOP_BLOCK_SECONDS = 5.0
PLANT_AT_SECONDS = 0.5
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


def _sync_session_factory(database_url: str):
    engine = create_engine(database_url, future=True)
    return engine, sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def _sync_plant_stale_processing(database_url: str, paper_id: str, *, updated_at: datetime) -> None:
    """Plant a PROCESSING zombie via sync SQL (usable while the asyncio loop is dead)."""
    engine, factory = _sync_session_factory(database_url)
    try:
        with factory() as session:
            paper = session.get(PaperRow, paper_id)
            if paper is None:
                paper = PaperRow(
                    paper_id=paper_id,
                    title="starve zombie",
                    status=PaperStatus.PROCESSING.value,
                    pdf_path=f"./uploads/{paper_id}.pdf",
                    updated_at=updated_at,
                    created_at=updated_at,
                )
                session.add(paper)
            else:
                paper.status = PaperStatus.PROCESSING.value
                paper.updated_at = updated_at

            run = session.get(PipelineRunRow, paper_id)
            if run is None:
                run = PipelineRunRow(
                    paper_id=paper_id,
                    stage=PipelineStage.EXTRACTING.value,
                    percent=STAGE_PERCENT[PipelineStage.EXTRACTING],
                    message="planted during loop starvation",
                    error_code=None,
                    failed_during=None,
                    head_refine_warnings=[],
                    classify_warnings=[],
                    extract_warnings=[],
                    updated_at=updated_at,
                    created_at=updated_at,
                )
                session.add(run)
            else:
                run.stage = PipelineStage.EXTRACTING.value
                run.percent = STAGE_PERCENT[PipelineStage.EXTRACTING]
                run.message = "planted during loop starvation"
                run.error_code = None
                run.failed_during = None
                run.updated_at = updated_at
            session.commit()
    finally:
        engine.dispose()


def _sync_read_heal_snapshot(
    database_url: str,
    paper_id: str,
) -> tuple[str | None, str | None, str | None, datetime | None]:
    """Fresh sync session read — proves durable COMMIT, not an in-memory dirty row."""
    engine, factory = _sync_session_factory(database_url)
    try:
        with factory() as session:
            paper = session.get(PaperRow, paper_id)
            run = session.get(PipelineRunRow, paper_id)
            status = None if paper is None else paper.status
            code = None if run is None else run.error_code
            stage = None if run is None else run.stage
            updated = None if run is None else run.updated_at
            return status, code, stage, updated
    finally:
        engine.dispose()


@pytest.mark.asyncio
@pytest.mark.process_release_gate
async def test_processing_watchdog_survives_loop_starvation(
    processing_starvation_db: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """系统级解耦：主 loop ``time.sleep(5)`` 假死视窗内，OS 线程看门狗仍 sync 捞库并 Commit。

    Deterministic proofs
    --------------------
    - Dedicated ``process-pipeline-watchdog`` thread keeps ticking while FastAPI's
      event-loop thread is hard-blocked (no asyncio Task progress).
    - Orphan planted mid-window is flipped to FAILED + ``PROCESS_TIMEOUT`` and the
      change is visible to a **new** sync SQL session before the main loop wakes —
      durable commit under physical thread decoupling.
    """
    caplog.set_level(logging.INFO)

    main_thread = threading.current_thread()
    register_main_event_loop(asyncio.get_running_loop())
    clear_processing_watchdog_tick_timestamps()
    stop_processing_watchdog()
    start_processing_watchdog()
    assert processing_watchdog_thread_is_alive()

    database_url = get_settings().database_url
    plant_done = threading.Event()
    probe_state: dict[str, object] = {
        "status": None,
        "error_code": None,
        "stage": None,
        "updated_at": None,
        "probe_mono": None,
        "watchdog_alive_at_probe": False,
    }
    thread_errors: list[BaseException] = []

    def _plant_zombie_during_starvation() -> None:
        try:
            time.sleep(PLANT_AT_SECONDS)
            stale = datetime.now(UTC) - timedelta(seconds=STUCK_AFTER_SECONDS + 5.0)
            _sync_plant_stale_processing(database_url, PAPER_P, updated_at=stale)
            plant_done.set()
        except BaseException as exc:  # noqa: BLE001 — surface into parent assertions
            thread_errors.append(exc)
            plant_done.set()

    def _probe_during_starvation() -> None:
        try:
            if not plant_done.wait(timeout=MAIN_LOOP_BLOCK_SECONDS):
                thread_errors.append(TimeoutError("zombie was not planted during starvation"))
                return
            # Leave enough wall-clock for ≥1 dedicated-thread scan after plant.
            time.sleep(max(0.0, PROBE_AT_SECONDS - PLANT_AT_SECONDS))
            probe_state["watchdog_alive_at_probe"] = processing_watchdog_thread_is_alive()
            status, code, stage, updated = _sync_read_heal_snapshot(database_url, PAPER_P)
            probe_state["status"] = status
            probe_state["error_code"] = code
            probe_state["stage"] = stage
            probe_state["updated_at"] = updated
            probe_state["probe_mono"] = time.monotonic()
        except BaseException as exc:  # noqa: BLE001 — surface into parent assertions
            thread_errors.append(exc)

    planter = threading.Thread(target=_plant_zombie_during_starvation, name="processing-starve-plant", daemon=True)
    probe = threading.Thread(target=_probe_during_starvation, name="processing-starve-probe", daemon=True)
    planter.start()
    probe.start()

    # Starve the main asyncio / FastAPI dispatch thread (false-async hard block).
    # No await / no cooperative yield — routes and all main-loop Tasks are frozen.
    block_started = time.monotonic()
    assert threading.current_thread() is main_thread
    time.sleep(MAIN_LOOP_BLOCK_SECONDS)
    block_ended = time.monotonic()
    assert block_ended - block_started >= MAIN_LOOP_BLOCK_SECONDS - 0.05

    planter.join(timeout=2.0)
    probe.join(timeout=2.0)
    stop_processing_watchdog()
    register_main_event_loop(None)

    assert not thread_errors, f"side threads failed: {thread_errors!r}"
    assert plant_done.is_set()

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
    dedicated_ticks = [
        r
        for r in tick_logs
        if getattr(r, "mode", None) == "dedicated_thread"
        or getattr(r, "thread_name", None) == PROCESSING_WATCHDOG_THREAD_NAME
    ]
    assert len(dedicated_ticks) >= 1, "watchdog ticks must advertise dedicated_thread mode"

    # Macro heal completed while the event loop was still fake-dead.
    probe_mono = probe_state["probe_mono"]
    assert isinstance(probe_mono, float)
    assert block_started < probe_mono < block_ended, (
        f"heal probe must land inside the {MAIN_LOOP_BLOCK_SECONDS}s starvation window "
        f"(started={block_started}, probe={probe_mono}, ended={block_ended})"
    )
    assert probe_state["watchdog_alive_at_probe"] is True
    assert probe_state["status"] == PaperStatus.FAILED.value
    assert probe_state["error_code"] == PROCESS_TIMEOUT_CODE
    assert probe_state["stage"] == PipelineStage.FAILED.value
    assert probe_state["updated_at"] is not None
    assert any(PROCESS_WATCHDOG_HEAL_TAG in r.getMessage() for r in caplog.records)

    # Post-wake re-read via yet another sync engine: durable COMMIT survived.
    final_status, final_code, final_stage, _ = _sync_read_heal_snapshot(database_url, PAPER_P)
    assert final_status == PaperStatus.FAILED.value
    assert final_code == PROCESS_TIMEOUT_CODE
    assert final_stage == PipelineStage.FAILED.value
