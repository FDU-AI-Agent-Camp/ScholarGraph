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
                                                          （``vector_cleanup_queue`` outbox 防重启丢任务）

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


def snapshot_wipe_target_run_ids(paper_id: str) -> set[str]:
    """Capture active + in-flight index run ids before abort / wipe."""
    targets: set[str] = set()
    active = get_paper_service().get_active_run_id(paper_id)
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


async def _execute_wave2_job(
    paper_id: str,
    run_id: str,
    *,
    delays_seconds: tuple[float, ...],
) -> None:
    """Run delayed delete_run retries, then ack the durable outbox row on success."""
    from backend.rag.handlers import _compensate_revoked_index_run

    await _compensate_revoked_index_run(paper_id, run_id, delays_seconds=delays_seconds)
    get_vector_cleanup_queue_repository().delete_by_paper_run_sync(paper_id, run_id)


def schedule_wipe_wave2_sweep(
    paper_id: str,
    run_ids: set[str] | frozenset[str] | list[str],
    *,
    delays_seconds: tuple[float, ...] | None = None,
) -> list[asyncio.Task[None]]:
    """Persist Wave-2 tombstones then schedule delayed ``delete_run`` (hot path).

    Durable enqueue happens first so a restart cannot drop the scrub. Default delay
    is ``PAPER_WIPE_VECTOR_SWEEP_DELAY_SECONDS`` (120s), with two short retries.
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
        task = asyncio.create_task(
            _execute_wave2_job(paper_id, run_id, delays_seconds=delays_seconds),
            name=f"wipe-wave2-sweep:{paper_id}:{run_id}",
        )
        _track_task(task)
        scheduled.append(task)
        logger.info(
            "wipe_wave2_sweep_scheduled",
            extra={
                "paper_id": paper_id,
                "run_id": run_id,
                "delays_seconds": list(delays_seconds),
                "outbox_inserted": inserted,
                "execute_at": execute_at.isoformat(),
            },
        )
    return scheduled


def _remaining_delay_seconds(job: VectorCleanupJob, *, now: datetime) -> float:
    return max(0.0, (job.execute_at - now).total_seconds())


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
            # Cold-boot due rows: scrub immediately (no extra 5s/10s wall wait).
            delays = (0.0,)
            due_count += 1
        else:
            delays = (remaining, remaining + 5.0, remaining + 10.0)
        task = asyncio.create_task(
            _execute_wave2_job(job.paper_id, job.run_id, delays_seconds=delays),
            name=f"wipe-wave2-startup:{job.paper_id}:{job.run_id}",
        )
        _track_task(task)

    logger.info(
        "vector_cleanup_queue_startup_reconcile",
        extra={"pending": len(jobs), "due": due_count},
    )


def reset_wipe_sweep_tasks_for_tests() -> None:
    """Cancel and clear tracked Wave-2 tasks (pytest isolation)."""
    for task in list(_WIPE_SWEEP_TASKS):
        if not task.done():
            task.cancel()
    _WIPE_SWEEP_TASKS.clear()
