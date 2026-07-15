"""Processing / pending orphan heal — cold-boot reconcile + wall-clock watchdog."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from backend.config import get_settings
from backend.db.base import get_async_session_factory
from backend.db.models import PaperRow, PipelineRunRow
from backend.graph.state import STAGE_PERCENT
from backend.pipeline.processing_watchdog import (
    PROCESS_ORPHANED_CODE,
    PROCESS_ORPHANED_MESSAGE,
    PROCESS_TIMEOUT_CODE,
    PROCESS_TIMEOUT_MESSAGE,
    QUEUE_TIMEOUT_CODE,
    QUEUE_TIMEOUT_MESSAGE,
    reconcile_processing_on_startup,
    reset_processing_watchdog_sync_engine,
    scan_and_fail_orphaned_processing,
    scan_and_fail_stuck_pending,
    scan_and_fail_stuck_processing,
    scan_and_fail_stuck_processing_sync,
    start_processing_watchdog,
    stop_processing_watchdog,
)
from backend.repositories.async_bridge import run_async
from backend.repositories.pipeline_repository import get_pipeline_repository
from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage
from backend.services.errors import PROCESS_ORPHANED_CODE as ERR_ORPHAN
from backend.services.errors import PROCESS_TIMEOUT_CODE as ERR_TIMEOUT
from backend.services.errors import QUEUE_TIMEOUT_CODE as ERR_QUEUE
from tests.helpers.persistence_testkit import (
    init_isolated_database,
    register_test_paper,
    reset_persistence_singletons,
)


@pytest.fixture
def processing_watchdog_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "processing_watchdog.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("SCHOLARGRAPH_IGNORE_DOTENV", "1")
    monkeypatch.setenv("PROCESS_WATCHDOG_ENABLED", "true")
    monkeypatch.setenv("PROCESS_WATCHDOG_SECONDS", "900")
    monkeypatch.setenv("PROCESS_WATCHDOG_INTERVAL_SECONDS", "60")
    monkeypatch.setenv("PROCESS_ORPHAN_GRACE_SECONDS", "10")
    monkeypatch.setenv("PENDING_QUEUE_TIMEOUT_SECONDS", "3600")
    get_settings.cache_clear()
    reset_persistence_singletons()
    reset_processing_watchdog_sync_engine()
    stop_processing_watchdog()
    run_async(init_isolated_database(db_path))
    yield
    stop_processing_watchdog()
    reset_processing_watchdog_sync_engine()
    reset_persistence_singletons()
    get_settings.cache_clear()


async def _put_paper_processing(
    paper_id: str,
    *,
    updated_at: datetime,
    stage: PipelineStage = PipelineStage.EXTRACTING,
) -> None:
    await register_test_paper(paper_id, status=PaperStatus.PENDING, with_status_row=True)
    snapshot = PaperStatusData(
        paper_id=paper_id,
        status=PaperStatus.PROCESSING,
        percent=STAGE_PERCENT[stage],
        stage=stage,
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


async def _put_paper_pending(paper_id: str, *, updated_at: datetime) -> None:
    await register_test_paper(paper_id, status=PaperStatus.PENDING, with_status_row=True)
    async with get_async_session_factory()() as session:
        run = await session.get(PipelineRunRow, paper_id)
        paper = await session.get(PaperRow, paper_id)
        assert run is not None and paper is not None
        run.updated_at = updated_at
        paper.updated_at = updated_at
        paper.status = PaperStatus.PENDING.value
        await session.commit()


def test_error_codes_are_stable() -> None:
    assert PROCESS_ORPHANED_CODE == ERR_ORPHAN == "PROCESS_ORPHANED"
    assert PROCESS_TIMEOUT_CODE == ERR_TIMEOUT == "PROCESS_TIMEOUT"
    assert QUEUE_TIMEOUT_CODE == ERR_QUEUE == "QUEUE_TIMEOUT"


@pytest.mark.asyncio
async def test_wall_clock_fails_stale_processing(processing_watchdog_db) -> None:
    now = datetime.now(UTC)
    stale = now - timedelta(seconds=901)
    fresh = now - timedelta(seconds=60)
    await _put_paper_processing("stale-proc", updated_at=stale)
    await _put_paper_processing("fresh-proc", updated_at=fresh)

    failed_ids = await scan_and_fail_stuck_processing(
        now=now,
        stuck_after_seconds=900.0,
    )
    assert failed_ids == ["stale-proc"]

    stale_row = await get_pipeline_repository().get_latest("stale-proc")
    assert stale_row is not None
    assert stale_row.status == PaperStatus.FAILED
    assert stale_row.error_code == PROCESS_TIMEOUT_CODE
    assert stale_row.message == PROCESS_TIMEOUT_MESSAGE
    assert stale_row.failed_during is not None
    assert stale_row.failed_during.value == PipelineStage.EXTRACTING.value

    fresh_row = await get_pipeline_repository().get_latest("fresh-proc")
    assert fresh_row is not None
    assert fresh_row.status == PaperStatus.PROCESSING


@pytest.mark.asyncio
@pytest.mark.process_release_gate
async def test_watchdog_slow_but_alive_extends_lease(processing_watchdog_db) -> None:
    """Unit/memory dual-check: stale paper + live registry Task → keep PROCESSING, bump lease."""
    from backend.services import pipeline_task_registry as registry

    registry.reset_pipeline_task_registry()
    now = datetime.now(UTC)
    stale = now - timedelta(seconds=950)
    paper_id = "slow-but-alive"
    await _put_paper_processing(paper_id, updated_at=stale)
    before = await get_pipeline_repository().get_latest(paper_id)
    assert before is not None
    before_updated = before.updated_at
    assert before_updated is not None
    if before_updated.tzinfo is None:
        before_updated = before_updated.replace(tzinfo=UTC)

    async def _hang() -> None:
        await asyncio.sleep(60)

    # Real asyncio.Task (not MagicMock) so is_paper_work_alive / cancelling() run production paths.
    live_task = asyncio.create_task(_hang(), name=f"pipeline-{paper_id}")
    registry.register_pipeline_task(paper_id, live_task)
    try:
        assert registry.is_paper_work_alive(paper_id)
        failed_ids = await scan_and_fail_stuck_processing(
            now=now,
            stuck_after_seconds=900.0,
        )
        assert failed_ids == []
        after = await get_pipeline_repository().get_latest(paper_id)
        assert after is not None
        assert after.status == PaperStatus.PROCESSING
        assert after.error_code is None
        assert after.updated_at is not None
        after_updated = after.updated_at
        if after_updated.tzinfo is None:
            after_updated = after_updated.replace(tzinfo=UTC)
        # Lease renewal uses wall-clock now (not the injected scan cutoff).
        assert after_updated > before_updated
        assert after_updated >= now
    finally:
        live_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await live_task
        registry.reset_pipeline_task_registry()


@pytest.mark.asyncio
@pytest.mark.process_release_gate
async def test_watchdog_true_zombie_triggers_failed(processing_watchdog_db) -> None:
    """Unit/memory dual-check: stale paper + empty registry → FAILED + PROCESS_TIMEOUT."""
    from backend.services.pipeline_task_registry import (
        get_pipeline_task,
        reset_pipeline_task_registry,
    )

    reset_pipeline_task_registry()
    now = datetime.now(UTC)
    stale = now - timedelta(seconds=950)
    paper_id = "true-zombie"
    await _put_paper_processing(paper_id, updated_at=stale)
    assert get_pipeline_task(paper_id) is None

    failed_ids = await scan_and_fail_stuck_processing(
        now=now,
        stuck_after_seconds=900.0,
    )
    assert failed_ids == [paper_id]
    row = await get_pipeline_repository().get_latest(paper_id)
    assert row is not None
    assert row.status == PaperStatus.FAILED
    assert row.error_code == PROCESS_TIMEOUT_CODE
    assert PROCESS_TIMEOUT_CODE in (row.error_code or "")
    assert row.message == PROCESS_TIMEOUT_MESSAGE


@pytest.mark.asyncio
async def test_wall_clock_renews_lease_when_pipeline_task_still_alive(
    processing_watchdog_db,
) -> None:
    """Stale updated_at + live asyncio Task → renew lease, do not PROCESS_TIMEOUT."""
    from backend.services.pipeline_task_registry import (
        register_pipeline_task,
        reset_pipeline_task_registry,
        unregister_pipeline_task,
    )

    now = datetime.now(UTC)
    stale = now - timedelta(seconds=901)
    paper_id = "slow-alive-proc"
    await _put_paper_processing(paper_id, updated_at=stale)
    before = await get_pipeline_repository().get_latest(paper_id)
    assert before is not None
    before_updated = before.updated_at

    async def _hang() -> None:
        await asyncio.sleep(60)

    task = asyncio.create_task(_hang(), name=f"pipeline-{paper_id}")
    register_pipeline_task(paper_id, task)
    try:
        failed_ids = await scan_and_fail_stuck_processing(
            now=now,
            stuck_after_seconds=900.0,
        )
        assert failed_ids == []
        after = await get_pipeline_repository().get_latest(paper_id)
        assert after is not None
        assert after.status == PaperStatus.PROCESSING
        assert after.error_code is None
        assert after.updated_at is not None
        assert before_updated is not None
        assert after.updated_at > before_updated
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        unregister_pipeline_task(paper_id, task)
        reset_pipeline_task_registry()


@pytest.mark.asyncio
async def test_wall_clock_aborts_then_fails_true_zombie(
    processing_watchdog_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cascading Kill: production force-cancel + abort must run before PROCESS_TIMEOUT SQL."""
    from backend.services import pipeline_task_registry as registry

    now = datetime.now(UTC)
    stale = now - timedelta(seconds=901)
    paper_id = "zombie-proc"
    await _put_paper_processing(paper_id, updated_at=stale)
    call_order: list[str] = []

    real_force = registry.force_cancel_paper_work_sync
    real_abort = registry.abort_in_flight_pipeline

    def _spy_force(pid: str) -> None:
        call_order.append(f"force:{pid}")
        real_force(pid)

    async def _spy_abort(pid: str) -> None:
        call_order.append(f"abort:{pid}")
        await real_abort(pid)

    monkeypatch.setattr(
        "backend.services.pipeline_task_registry.force_cancel_paper_work_sync",
        _spy_force,
    )
    monkeypatch.setattr(
        "backend.services.pipeline_task_registry.abort_in_flight_pipeline",
        _spy_abort,
    )

    failed_ids = await scan_and_fail_stuck_processing(
        now=now,
        stuck_after_seconds=900.0,
    )
    assert failed_ids == [paper_id]
    assert call_order == [f"force:{paper_id}", f"abort:{paper_id}"]
    row = await get_pipeline_repository().get_latest(paper_id)
    assert row is not None
    assert row.status == PaperStatus.FAILED
    assert row.error_code == PROCESS_TIMEOUT_CODE


@pytest.mark.asyncio
@pytest.mark.process_release_gate
async def test_watchdog_kill_execution_order(processing_watchdog_db, monkeypatch: pytest.MonkeyPatch) -> None:
    """Cascading Kill: abort (and lock release) must finish before SQL PROCESS_TIMEOUT."""
    from backend.services import pipeline_task_registry as registry
    from backend.services.paper_service import get_paper_service
    from backend.services.reextract_service import (
        is_reextract_inflight,
        reset_reextract_inflight_gate,
    )

    reset_reextract_inflight_gate()
    registry.reset_pipeline_task_registry()

    now = datetime.now(UTC)
    stale = now - timedelta(seconds=950)
    paper_id = "kill-order-zombie"
    await _put_paper_processing(paper_id, updated_at=stale)

    paper_lock = asyncio.Lock()
    lock_held = asyncio.Event()
    call_order: list[str] = []

    async def _zombie_holding_lock() -> None:
        async with paper_lock:
            lock_held.set()
            await asyncio.sleep(3600)

    zombie_task = asyncio.create_task(_zombie_holding_lock(), name=f"pipeline-{paper_id}")
    await asyncio.wait_for(lock_held.wait(), timeout=1.0)
    registry.register_pipeline_task(paper_id, zombie_task)

    # Simulate an abandoned reextract claim (mutex not returned after worker death).
    from backend.services import reextract_service as rex

    rex._reextract_inflight.add(paper_id)
    assert is_reextract_inflight(paper_id)

    real_abort = registry.abort_in_flight_pipeline
    paper_service = get_paper_service()
    real_fail = paper_service.fail_orphaned_pipeline_paper_sync

    async def _spy_abort(pid: str) -> None:
        call_order.append("abort_start")
        await real_abort(pid)
        call_order.append("abort_done")

    def _spy_fail(pid: str, *, error_code: str, message: str) -> bool:
        call_order.append("sql_fail")
        return real_fail(pid, error_code=error_code, message=message)

    monkeypatch.setattr(
        "backend.services.pipeline_task_registry.abort_in_flight_pipeline",
        _spy_abort,
    )
    monkeypatch.setattr(
        paper_service,
        "fail_orphaned_pipeline_paper_sync",
        _spy_fail,
    )

    bystander_acquired = asyncio.Event()

    async def _bystander_reclaim_lock() -> None:
        async with paper_lock:
            bystander_acquired.set()

    bystander = asyncio.create_task(_bystander_reclaim_lock(), name="bystander-lock")
    # Schedule bystander so it blocks on paper_lock while the zombie still holds it.
    await asyncio.sleep(0)
    assert paper_lock.locked()
    assert not bystander_acquired.is_set()

    # Inject CancelledError so vitality dual-check treats the Task as non-live,
    # but do not yield — finally (and lock release) must wait for abort's await.
    zombie_task.cancel()
    assert not registry.is_paper_work_alive(paper_id)

    failed_ids = await scan_and_fail_stuck_processing(
        now=now,
        stuck_after_seconds=900.0,
    )
    assert failed_ids == [paper_id]
    assert "abort_start" in call_order
    assert "abort_done" in call_order
    assert "sql_fail" in call_order
    assert call_order.index("abort_done") < call_order.index("sql_fail")

    await asyncio.wait_for(bystander_acquired.wait(), timeout=1.0)
    await asyncio.wait_for(bystander, timeout=1.0)
    assert not is_reextract_inflight(paper_id)

    row = await get_pipeline_repository().get_latest(paper_id)
    assert row is not None
    assert row.status == PaperStatus.FAILED
    assert row.error_code == PROCESS_TIMEOUT_CODE

    registry.reset_pipeline_task_registry()
    reset_reextract_inflight_gate()


@pytest.mark.asyncio
async def test_cascade_kill_releases_reextract_claim_before_sql_fail(
    processing_watchdog_db,
) -> None:
    """Lock eviction: reextract claim must be clear when SQL flips to failed."""
    from backend.services.reextract_service import (
        is_reextract_inflight,
        release_reextract_claim_for_abort,
        reset_reextract_inflight_gate,
    )

    reset_reextract_inflight_gate()
    now = datetime.now(UTC)
    stale = now - timedelta(seconds=901)
    paper_id = "zombie-with-claim"
    await _put_paper_processing(paper_id, updated_at=stale)
    # Simulate a stuck claim without holding the asyncio Lock across the test.
    from backend.services import reextract_service as rex

    rex._reextract_inflight.add(paper_id)
    assert is_reextract_inflight(paper_id)

    failed_ids = await scan_and_fail_stuck_processing(
        now=now,
        stuck_after_seconds=900.0,
    )
    assert failed_ids == [paper_id]
    assert not is_reextract_inflight(paper_id)
    release_reextract_claim_for_abort(paper_id)  # idempotent
    reset_reextract_inflight_gate()


@pytest.mark.asyncio
async def test_wall_clock_processing_scan_skips_pending(processing_watchdog_db) -> None:
    """Dedicated PROCESSING timeout path must not mis-label pending as PROCESS_TIMEOUT."""
    now = datetime.now(UTC)
    stale = now - timedelta(hours=2)
    await _put_paper_pending("stale-pending", updated_at=stale)

    failed_ids = await scan_and_fail_stuck_processing(
        now=now,
        stuck_after_seconds=900.0,
    )
    assert failed_ids == []
    latest = await get_pipeline_repository().get_latest("stale-pending")
    assert latest is not None
    assert latest.status == PaperStatus.PENDING


@pytest.mark.asyncio
@pytest.mark.process_release_gate
async def test_wall_clock_fails_stale_pending_as_queue_timeout(processing_watchdog_db) -> None:
    now = datetime.now(UTC)
    stale = now - timedelta(seconds=3601)
    fresh = now - timedelta(seconds=600)
    await _put_paper_pending("stale-q", updated_at=stale)
    await _put_paper_pending("fresh-q", updated_at=fresh)

    failed_ids = await scan_and_fail_stuck_pending(now=now, stuck_after_seconds=3600.0)
    assert failed_ids == ["stale-q"]

    stale_row = await get_pipeline_repository().get_latest("stale-q")
    assert stale_row is not None
    assert stale_row.status == PaperStatus.FAILED
    assert stale_row.error_code == QUEUE_TIMEOUT_CODE
    assert stale_row.message == QUEUE_TIMEOUT_MESSAGE

    fresh_row = await get_pipeline_repository().get_latest("fresh-q")
    assert fresh_row is not None
    assert fresh_row.status == PaperStatus.PENDING


@pytest.mark.asyncio
@pytest.mark.process_release_gate
async def test_cold_boot_spares_fresh_pending_within_grace(processing_watchdog_db) -> None:
    """Rolling-update safety: updated_at within ε of boot must not be force-failed."""
    now = datetime.now(UTC)
    within_grace = now - timedelta(seconds=3)
    await _put_paper_pending("fresh-pending", updated_at=within_grace)
    await _put_paper_processing("fresh-proc", updated_at=within_grace)

    failed_ids = await scan_and_fail_orphaned_processing(now=now)
    assert failed_ids == []

    for pid in ("fresh-pending", "fresh-proc"):
        latest = await get_pipeline_repository().get_latest(pid)
        assert latest is not None
        assert latest.status in {PaperStatus.PENDING, PaperStatus.PROCESSING}


@pytest.mark.asyncio
async def test_cold_boot_reconcile_fails_stale_pending_and_processing(
    processing_watchdog_db,
) -> None:
    now = datetime.now(UTC)
    stale = now - timedelta(seconds=30)
    await _put_paper_pending("orphan-pending", updated_at=stale)
    await _put_paper_processing("orphan-proc", updated_at=stale)

    failed_ids = await reconcile_processing_on_startup()
    assert set(failed_ids) == {"orphan-pending", "orphan-proc"}

    for pid in failed_ids:
        latest = await get_pipeline_repository().get_latest(pid)
        assert latest is not None
        assert latest.status == PaperStatus.FAILED
        assert latest.error_code == PROCESS_ORPHANED_CODE
        assert latest.message == PROCESS_ORPHANED_MESSAGE


@pytest.mark.asyncio
async def test_cold_boot_lifespan_clears_processing_zombies(
    processing_watchdog_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale = datetime.now(UTC) - timedelta(hours=2)
    await _put_paper_pending("life-pending", updated_at=stale)
    await _put_paper_processing("life-proc", updated_at=stale)

    async def _noop_probe(_settings) -> None:
        return None

    monkeypatch.setattr(
        "backend.startup.profile_validation.probe_reranker_connectivity",
        _noop_probe,
    )
    monkeypatch.setattr(
        "backend.rag.hybrid_retriever.create_hybrid_retriever",
        lambda: object(),
    )
    monkeypatch.setattr("backend.rag.hybrid_retriever.bind_hybrid_retriever", lambda _r: None)
    monkeypatch.setattr("backend.rag.hybrid_retriever.reset_hybrid_retriever", lambda: None)

    from backend.main import create_app, lifespan

    app = create_app()
    async with lifespan(app):
        for pid in ("life-pending", "life-proc"):
            latest = await get_pipeline_repository().get_latest(pid)
            assert latest is not None
            assert latest.status == PaperStatus.FAILED, pid
            assert latest.error_code == PROCESS_ORPHANED_CODE


def test_sync_scan_fails_stale_processing_and_pending(processing_watchdog_db) -> None:
    now = datetime.now(UTC)
    stale_proc = now - timedelta(seconds=1000)
    stale_pending = now - timedelta(seconds=4000)
    run_async(_put_paper_processing("sync-stale", updated_at=stale_proc))
    run_async(_put_paper_pending("sync-pending", updated_at=stale_pending))

    failed = scan_and_fail_stuck_processing_sync(
        now=now,
        stuck_after_seconds=900.0,
        pending_stuck_after_seconds=3600.0,
    )
    assert set(failed) == {"sync-stale", "sync-pending"}

    proc = run_async(get_pipeline_repository().get_latest("sync-stale"))
    assert proc is not None and proc.error_code == PROCESS_TIMEOUT_CODE
    pend = run_async(get_pipeline_repository().get_latest("sync-pending"))
    assert pend is not None and pend.error_code == QUEUE_TIMEOUT_CODE


def test_start_stop_processing_watchdog_thread(processing_watchdog_db, monkeypatch: pytest.MonkeyPatch) -> None:
    import threading
    import time

    from backend.pipeline.processing_watchdog import (
        PROCESSING_WATCHDOG_THREAD_NAME,
        processing_watchdog_thread_is_alive,
    )

    monkeypatch.setenv("PROCESS_WATCHDOG_INTERVAL_SECONDS", "0.05")
    get_settings.cache_clear()
    scan_calls = {"n": 0}

    def _counting_scan(**_kwargs):
        scan_calls["n"] += 1
        return []

    monkeypatch.setattr(
        "backend.pipeline.processing_watchdog.scan_and_fail_stuck_processing_sync",
        _counting_scan,
    )
    start_processing_watchdog()
    assert processing_watchdog_thread_is_alive()
    assert PROCESSING_WATCHDOG_THREAD_NAME in {t.name for t in threading.enumerate()}
    deadline = time.monotonic() + 2.0
    while scan_calls["n"] < 1 and time.monotonic() < deadline:
        time.sleep(0.05)
    stop_processing_watchdog()
    assert scan_calls["n"] >= 1
    assert not processing_watchdog_thread_is_alive()


@pytest.mark.asyncio
async def test_cold_boot_drains_orphan_batches_beyond_single_limit(
    processing_watchdog_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Startup must loop past the 200-row list cap instead of leaving zombies for reboot #2."""
    from backend.pipeline import processing_watchdog as pw
    from backend.services.paper_service import get_paper_service

    batch1 = [f"orphan-batch-a-{i}" for i in range(pw.COLD_BOOT_ORPHAN_BATCH_LIMIT)]
    batch2 = [f"orphan-batch-b-{i}" for i in range(3)]
    calls: list[int] = []

    async def _paged_list(*, older_than=None, limit: int = 200):  # noqa: ANN001
        _ = older_than
        calls.append(limit)
        if len(calls) == 1:
            return list(batch1)
        if len(calls) == 2:
            return list(batch2)
        return []

    async def _fail(paper_id: str, **_kwargs) -> bool:
        _ = paper_id
        return True

    service = get_paper_service()
    monkeypatch.setattr(service, "list_orphan_pipeline_paper_ids", _paged_list)
    monkeypatch.setattr(service, "fail_orphaned_pipeline_paper", _fail)

    failed = await scan_and_fail_orphaned_processing()
    assert len(calls) == 2
    assert calls[0] == pw.COLD_BOOT_ORPHAN_BATCH_LIMIT
    assert set(failed) == set(batch1) | set(batch2)
