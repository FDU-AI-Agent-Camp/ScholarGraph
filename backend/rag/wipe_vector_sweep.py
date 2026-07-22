# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Force wipe data-lifecycle — claim ∪ read isolation ∪ two-wave sweep.

Closed-loop blueprint for force DELETE / force reextract under asyncio + Chroma
``to_thread`` (cannot XA-cancel in-flight C upserts)::

    场景维度          重构前（脆弱）                         重构后（工业级韧性）
    --------------    ----------------------------------  ---------------------------------
    并发 Claim 拦截   进程内 set 跨 worker 失效，双开重抽   ``paper_ops_claims`` 集群互斥；409
    迟到写入处理      旧线程 upsert 污染新跑 / 无主驻留      ``index_run_id`` + active 读时过滤；
                                                          无 active 则 fail-closed（幽灵失明）
    存储空间回收      依赖运气 / 人工清库                      Wave1 ``delete_by_paper`` +
                                                          Wave2 T+120s ``delete_run`` 扫墓
                                                          （``vector_cleanup_queue`` outbox）

Consistency boundary (not XA)::

    DELETE 204 means Wave-1 paper-scoped purge already ran. Wave-2 is *eventual*
    compensation for late ``to_thread`` upserts (default ~120s). The outbox survives
    process death; it does **not** make the 204 response instantaneously zero-vector
    across the whole cluster.

Call order on wipe (must not reverse)::

    1. snapshot wipe target run ids (active ∪ inflight)
    2. acquire paper_ops_claims (delete ∪ reextract)
    3. abort_in_flight_pipeline (Task cancel + indexing revoke)
    4. extend wipe targets with sticky-revoked run id
    5. Wave 1 — ``delete_by_paper`` (immediate)
    6. Wave 2 — ``schedule_wipe_wave2_sweep`` (outbox + delayed delete_run)
    7. disk / SQL cascade or reextract reset + reschedule
    8. release paper_ops_claims owner token
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from backend.config import get_settings
from backend.rag.indexing_run_registry import get_indexing_run_registry
from backend.repositories.vector_cleanup_queue_repository import (
    VectorCleanupJob,
    get_vector_cleanup_queue_repository,
)
from backend.services.paper_service import get_paper_service

logger = logging.getLogger(__name__)

# Track fire-and-forget tasks so they are not GC'd mid-flight.
_WIPE_SWEEP_TASKS: set[asyncio.Task[None]] = set()
# Process-local only: multi-worker may each spawn once for the same due row;
# ``delete_run`` is idempotent, so that is waste not a correctness hole.
_INFLIGHT_KEYS: set[tuple[str, str]] = set()
_POLL_TASK: asyncio.Task[None] | None = None
_POLL_STOP: asyncio.Event | None = None

# Long-lived demo: retry due outbox rows without waiting for the next process restart.
VECTOR_CLEANUP_POLL_INTERVAL_SECONDS = 30.0


async def snapshot_wipe_target_run_ids(paper_id: str) -> set[str]:
    """Capture active + in-flight index run ids before abort / wipe."""
    targets: set[str] = set()
    active = await get_paper_service().get_active_run_id(paper_id)
    if active:
        targets.add(active)
    inflight = get_indexing_run_registry().peek_inflight(paper_id)
    if inflight:
        targets.add(inflight)
    return targets


def extend_wipe_targets_after_abort(paper_id: str, targets: set[str]) -> set[str]:
    """Merge sticky-revoked run id after ``abort_in_flight_pipeline``."""
    revoked = get_indexing_run_registry().revoke(paper_id)
    if revoked:
        targets.add(revoked)
    return targets


def _track_task(task: asyncio.Task[None]) -> None:
    _WIPE_SWEEP_TASKS.add(task)
    task.add_done_callback(_WIPE_SWEEP_TASKS.discard)


def _try_begin_inflight(paper_id: str, run_id: str) -> bool:
    key = (paper_id, run_id)
    if key in _INFLIGHT_KEYS:
        return False
    _INFLIGHT_KEYS.add(key)
    return True


def _end_inflight(paper_id: str, run_id: str) -> None:
    _INFLIGHT_KEYS.discard((paper_id, run_id))


async def _execute_wave2_job(
    paper_id: str,
    run_id: str,
    *,
    delays_seconds: tuple[float, ...],
) -> None:
    """Run delayed delete_run retries, then ack the durable outbox row on success."""
    from backend.rag.handlers import _compensate_revoked_index_run

    try:
        await _compensate_revoked_index_run(paper_id, run_id, delays_seconds=delays_seconds)
        get_vector_cleanup_queue_repository().delete_by_paper_run_sync(paper_id, run_id)
    except Exception as exc:  # noqa: BLE001 — continue sweep loop for other orphan runs
        logger.warning(
            "wipe_vector_run_failed",
            extra={
                "run_id": run_id,
                "paper_id": paper_id,
                "attempt": len(delays_seconds),
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
            exc_info=True,
        )
    finally:
        _end_inflight(paper_id, run_id)


def _spawn_wave2_job(
    paper_id: str,
    run_id: str,
    *,
    delays_seconds: tuple[float, ...],
    task_name: str,
) -> asyncio.Task[None] | None:
    if not _try_begin_inflight(paper_id, run_id):
        logger.info(
            "wipe_wave2_sweep_skip_inflight",
            extra={"paper_id": paper_id, "run_id": run_id},
        )
        return None
    task = asyncio.create_task(
        _execute_wave2_job(paper_id, run_id, delays_seconds=delays_seconds),
        name=task_name,
    )
    _track_task(task)
    return task


def schedule_wipe_wave2_sweep(
    paper_id: str,
    run_ids: set[str] | frozenset[str] | list[str],
    *,
    delays_seconds: tuple[float, ...] | None = None,
) -> list[asyncio.Task[None]]:
    """Persist Wave-2 tombstones then schedule delayed ``delete_run`` (hot path).

    Durable enqueue happens first so a restart cannot drop the scrub. If the
    ``(paper_id, run_id)`` row already exists, skip ``create_task`` (idempotent;
    the existing worker / poller owns the scrub). Default delay is
    ``PAPER_WIPE_VECTOR_SWEEP_DELAY_SECONDS`` (120s), with two short retries.
    """
    settings = get_settings()
    primary = float(settings.paper_wipe_vector_sweep_delay_seconds)
    if delays_seconds is None:
        delays_seconds = (primary, primary + 5.0, primary + 10.0)

    first_delay = float(delays_seconds[0]) if delays_seconds else primary
    now = datetime.now(UTC)
    execute_at = now + timedelta(seconds=max(0.0, first_delay))
    repo = get_vector_cleanup_queue_repository()

    scheduled: list[asyncio.Task[None]] = []
    for run_id in sorted({rid for rid in run_ids if rid}):
        inserted = repo.enqueue_sync(paper_id, run_id, execute_at=execute_at, create_at=now)
        if not inserted:
            logger.info(
                "wipe_wave2_sweep_skip_duplicate_outbox",
                extra={"paper_id": paper_id, "run_id": run_id},
            )
            continue
        task = _spawn_wave2_job(
            paper_id,
            run_id,
            delays_seconds=delays_seconds,
            task_name=f"wipe-wave2-sweep:{paper_id}:{run_id}",
        )
        if task is not None:
            scheduled.append(task)
            logger.info(
                "wipe_wave2_sweep_scheduled",
                extra={
                    "paper_id": paper_id,
                    "run_id": run_id,
                    "delays_seconds": list(delays_seconds),
                    "outbox_inserted": True,
                    "execute_at": execute_at.isoformat(),
                },
            )
    return scheduled


def _remaining_delay_seconds(job: VectorCleanupJob, *, now: datetime) -> float:
    return max(0.0, (job.execute_at - now).total_seconds())


async def drain_due_vector_cleanup_jobs() -> int:
    """Scrub outbox rows with ``execute_at <= now`` that are not already in-flight.

    Used by the periodic poller so a failed compensate while the process stays up
    does not wait for the next cold boot.
    """
    due = get_vector_cleanup_queue_repository().list_due_sync()
    spawned = 0
    for job in due:
        task = _spawn_wave2_job(
            job.paper_id,
            job.run_id,
            delays_seconds=(0.0,),
            task_name=f"wipe-wave2-due:{job.paper_id}:{job.run_id}",
        )
        if task is not None:
            spawned += 1
    return spawned


async def reconcile_vector_cleanup_on_startup() -> None:
    """Cold-boot drain: due outbox rows scrub immediately; future rows re-arm timers."""
    now = datetime.now(UTC)
    jobs = get_vector_cleanup_queue_repository().list_pending_sync()
    if not jobs:
        return

    due_count = 0
    for job in jobs:
        remaining = _remaining_delay_seconds(job, now=now)
        if remaining <= 0:
            delays = (0.0,)
            due_count += 1
        else:
            delays = (remaining, remaining + 5.0, remaining + 10.0)
        _spawn_wave2_job(
            job.paper_id,
            job.run_id,
            delays_seconds=delays,
            task_name=f"wipe-wave2-startup:{job.paper_id}:{job.run_id}",
        )

    logger.info(
        "vector_cleanup_queue_startup_reconcile",
        extra={"pending": len(jobs), "due": due_count},
    )


async def _vector_cleanup_poll_loop(interval_seconds: float) -> None:
    assert _POLL_STOP is not None
    while not _POLL_STOP.is_set():
        try:
            spawned = await drain_due_vector_cleanup_jobs()
            if spawned:
                logger.info(
                    "vector_cleanup_queue_poll_drain",
                    extra={"spawned": spawned},
                )
        except Exception as exc:  # noqa: BLE001 — continue sweep loop for other orphan runs
            logger.warning(
                "vector_cleanup_queue_poll_failed",
                extra={
                    "interval_seconds": interval_seconds,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
                exc_info=True,
            )
        try:
            await asyncio.wait_for(_POLL_STOP.wait(), timeout=interval_seconds)
            break
        except TimeoutError:
            continue


def start_vector_cleanup_poller(
    *,
    interval_seconds: float = VECTOR_CLEANUP_POLL_INTERVAL_SECONDS,
) -> None:
    """Idempotently start the in-process due-outbox poller (long-lived demo path)."""
    global _POLL_TASK, _POLL_STOP
    if _POLL_TASK is not None and not _POLL_TASK.done():
        return
    _POLL_STOP = asyncio.Event()
    _POLL_TASK = asyncio.create_task(
        _vector_cleanup_poll_loop(max(1.0, float(interval_seconds))),
        name="vector-cleanup-outbox-poller",
    )
    _track_task(_POLL_TASK)
    logger.info(
        "vector_cleanup_poller_started",
        extra={"interval_seconds": interval_seconds},
    )


def stop_vector_cleanup_poller() -> None:
    """Signal the due-outbox poller to stop (lifespan / pytest teardown)."""
    global _POLL_TASK, _POLL_STOP
    if _POLL_STOP is not None:
        _POLL_STOP.set()
    task = _POLL_TASK
    _POLL_TASK = None
    _POLL_STOP = None
    if task is not None and not task.done():
        task.cancel()


def reset_wipe_sweep_tasks_for_tests() -> None:
    """Cancel and clear tracked Wave-2 tasks (pytest isolation)."""
    stop_vector_cleanup_poller()
    for task in list(_WIPE_SWEEP_TASKS):
        if not task.done():
            task.cancel()
    _WIPE_SWEEP_TASKS.clear()
    _INFLIGHT_KEYS.clear()
