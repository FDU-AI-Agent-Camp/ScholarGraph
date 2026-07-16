"""Wave-2 vector_cleanup_queue outbox — durable scrub across restarts."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from backend.rag.wipe_vector_sweep import (
    reconcile_vector_cleanup_on_startup,
    reset_wipe_sweep_tasks_for_tests,
    schedule_wipe_wave2_sweep,
)
from backend.repositories.vector_cleanup_queue_repository import (
    get_vector_cleanup_queue_repository,
    reset_vector_cleanup_queue_repository,
)


@pytest.fixture(autouse=True)
def _reset_outbox(persistence_env) -> None:
    reset_wipe_sweep_tasks_for_tests()
    reset_vector_cleanup_queue_repository()
    get_vector_cleanup_queue_repository().clear_all_sync()
    yield
    reset_wipe_sweep_tasks_for_tests()
    get_vector_cleanup_queue_repository().clear_all_sync()
    reset_vector_cleanup_queue_repository()


@pytest.mark.asyncio
async def test_schedule_wave2_persists_outbox_before_task(persistence_env) -> None:
    """Force wipe must leave a DB tombstone even if the in-memory task is cancelled."""
    paper_id = "outbox-persist"
    run_id = "run_ghost"

    with patch("backend.rag.handlers._compensate_revoked_index_run", return_value=None):
        tasks = schedule_wipe_wave2_sweep(paper_id, {run_id}, delays_seconds=(30.0,))
        assert len(tasks) == 1
        pending = get_vector_cleanup_queue_repository().list_pending_sync()
        assert len(pending) == 1
        assert pending[0].paper_id == paper_id
        assert pending[0].run_id == run_id
        assert pending[0].execute_at > datetime.now(UTC)
        tasks[0].cancel()
        with pytest.raises(asyncio.CancelledError):
            await tasks[0]
        # Tombstone survives task cancellation (restart simulation).
        still = get_vector_cleanup_queue_repository().list_pending_sync()
        assert len(still) == 1


@pytest.mark.asyncio
async def test_startup_reconcile_drains_due_outbox_rows(persistence_env) -> None:
    """Cold boot must scrub execute_at <= now rows left by a killed process."""
    paper_id = "outbox-startup"
    run_id = "run_due"
    repo = get_vector_cleanup_queue_repository()
    past = datetime.now(UTC) - timedelta(seconds=5)
    assert repo.enqueue_sync(paper_id, run_id, execute_at=past, create_at=past)

    cleaned: list[tuple[str, str]] = []

    async def _fake_compensate(pid: str, rid: str, *, delays_seconds: tuple[float, ...] = ()) -> None:
        cleaned.append((pid, rid))
        for delay in delays_seconds:
            if delay > 0:
                await asyncio.sleep(delay)

    with patch("backend.rag.handlers._compensate_revoked_index_run", _fake_compensate):
        await reconcile_vector_cleanup_on_startup()
        from backend.rag.wipe_vector_sweep import _WIPE_SWEEP_TASKS

        await asyncio.gather(*list(_WIPE_SWEEP_TASKS), return_exceptions=True)

    assert cleaned == [(paper_id, run_id)]
    assert repo.list_pending_sync() == []


@pytest.mark.asyncio
async def test_wave2_ack_removes_outbox_after_success(persistence_env) -> None:
    paper_id = "outbox-ack"
    run_id = "run_ack"

    async def _fake_compensate(pid: str, rid: str, *, delays_seconds: tuple[float, ...] = ()) -> None:
        _ = (pid, rid, delays_seconds)

    with patch("backend.rag.handlers._compensate_revoked_index_run", _fake_compensate):
        tasks = schedule_wipe_wave2_sweep(paper_id, {run_id}, delays_seconds=(0.01,))
        await asyncio.gather(*tasks)

    assert get_vector_cleanup_queue_repository().list_pending_sync() == []


@pytest.mark.asyncio
async def test_duplicate_enqueue_does_not_spawn_second_task(persistence_env) -> None:
    """Same (paper_id, run_id) must not create_task twice while outbox row exists."""
    paper_id = "outbox-dedupe"
    run_id = "run_dup"

    async def _slow_compensate(pid: str, rid: str, *, delays_seconds: tuple[float, ...] = ()) -> None:
        _ = (pid, rid)
        await asyncio.sleep(0.2)

    with patch("backend.rag.handlers._compensate_revoked_index_run", _slow_compensate):
        first = schedule_wipe_wave2_sweep(paper_id, {run_id}, delays_seconds=(0.05,))
        second = schedule_wipe_wave2_sweep(paper_id, {run_id}, delays_seconds=(0.05,))
        assert len(first) == 1
        assert second == []
        await asyncio.gather(*first)


@pytest.mark.asyncio
async def test_drain_due_retries_after_failed_compensate(persistence_env) -> None:
    """Process-alive path: failed scrub leaves outbox; poller drain retries without reboot."""
    from backend.rag.wipe_vector_sweep import drain_due_vector_cleanup_jobs

    paper_id = "outbox-retry"
    run_id = "run_fail_then_ok"
    repo = get_vector_cleanup_queue_repository()
    past = datetime.now(UTC) - timedelta(seconds=1)
    assert repo.enqueue_sync(paper_id, run_id, execute_at=past, create_at=past)

    calls = {"n": 0}

    async def _flaky(pid: str, rid: str, *, delays_seconds: tuple[float, ...] = ()) -> None:
        _ = (pid, rid, delays_seconds)
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("chroma blip")

    with patch("backend.rag.handlers._compensate_revoked_index_run", _flaky):
        spawned = await drain_due_vector_cleanup_jobs()
        assert spawned == 1
        from backend.rag.wipe_vector_sweep import _WIPE_SWEEP_TASKS

        await asyncio.gather(*list(_WIPE_SWEEP_TASKS), return_exceptions=True)
        assert repo.list_pending_sync()  # still due after failure

        spawned2 = await drain_due_vector_cleanup_jobs()
        assert spawned2 == 1
        await asyncio.gather(*list(_WIPE_SWEEP_TASKS), return_exceptions=True)

    assert calls["n"] == 2
    assert repo.list_pending_sync() == []
