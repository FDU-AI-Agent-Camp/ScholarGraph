"""Processing / pending orphan heal — cold-boot reconcile + wall-clock watchdog.

Cold-boot tombs ``updated_at < boot − ε``. Daemon: PROCESSING → PROCESS_TIMEOUT
(after vitality dual-check); PENDING → QUEUE_TIMEOUT. No silent requeue.

Vitality: stale ``updated_at`` + live Task probe → lease renew; true zombie →
Cascading Kill (cancel → claim eviction → SQL fail, clearing generation token).

Ops loop: dual-check prevents LLM false kills; abort before SQL; generation
guard blocks cross-worker orphan finalize; keep ~900s watchdog with renewals.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from datetime import UTC, datetime, timedelta

from backend.config import get_settings
from backend.repositories.async_bridge import get_registered_main_event_loop
from backend.repositories.pipeline_sync import reset_pipeline_sync_engine
from backend.services.errors import (
    PROCESS_ORPHANED_CODE,
    PROCESS_ORPHANED_MESSAGE,
    PROCESS_TIMEOUT_CODE,
    PROCESS_TIMEOUT_MESSAGE,
    QUEUE_TIMEOUT_CODE,
    QUEUE_TIMEOUT_MESSAGE,
)

logger = logging.getLogger(__name__)

PROCESS_WATCHDOG_HEAL_TAG = "[PROCESS_WATCHDOG_HEAL]"
PROCESSING_WATCHDOG_TICK_LOG = "processing_watchdog_tick"
PROCESSING_WATCHDOG_LEASE_LOG = "processing_watchdog_lease_extended"
_WATCHDOG_THREAD_STOP = threading.Event()
_WATCHDOG_THREAD: threading.Thread | None = None
_WATCHDOG_THREAD_LOCK = threading.Lock()
WATCHDOG_THREAD_JOIN_TIMEOUT_SECONDS = 5.0
PROCESSING_WATCHDOG_THREAD_NAME = "process-pipeline-watchdog"
_MAX_TICK_TIMESTAMPS = 256
_WATCHDOG_TICK_MONOTONIC: deque[float] = deque(maxlen=_MAX_TICK_TIMESTAMPS)
# Cold-boot list queries cap at 200; drain in rounds so a large zombie pile needs one boot.
COLD_BOOT_ORPHAN_BATCH_LIMIT = 200
COLD_BOOT_ORPHAN_MAX_ROUNDS = 50


def reset_processing_watchdog_sync_engine() -> None:
    """Test helper: drop cached sync engine after DATABASE_URL changes."""
    reset_pipeline_sync_engine()


def processing_watchdog_tick_monotonic_timestamps() -> list[float]:
    """Test helper: monotonic timestamps of dedicated-thread ticks."""
    return list(_WATCHDOG_TICK_MONOTONIC)


def clear_processing_watchdog_tick_timestamps() -> None:
    """Test helper: reset recorded tick timestamps."""
    _WATCHDOG_TICK_MONOTONIC.clear()


def _cutoff_before(
    *,
    now: datetime | None = None,
    after_seconds: float,
) -> datetime:
    clock = now or datetime.now(UTC)
    return clock - timedelta(seconds=after_seconds)


def _process_stuck_older_than(
    *,
    now: datetime | None = None,
    stuck_after_seconds: float | None = None,
) -> datetime:
    settings = get_settings()
    stuck_s = stuck_after_seconds if stuck_after_seconds is not None else settings.process_watchdog_seconds
    return _cutoff_before(now=now, after_seconds=stuck_s)


def _pending_stuck_older_than(
    *,
    now: datetime | None = None,
    stuck_after_seconds: float | None = None,
) -> datetime:
    settings = get_settings()
    stuck_s = stuck_after_seconds if stuck_after_seconds is not None else settings.pending_queue_timeout_seconds
    return _cutoff_before(now=now, after_seconds=stuck_s)


def _cold_boot_older_than(*, now: datetime | None = None) -> datetime:
    """``t_boot − ε`` — only rows older than this grace window may be orphaned."""
    settings = get_settings()
    return _cutoff_before(now=now, after_seconds=float(settings.process_orphan_grace_seconds))


async def scan_and_fail_orphaned_processing(
    *,
    now: datetime | None = None,
) -> list[str]:
    """Fail leftover pending/processing with ``updated_at < boot − ε`` (cold-boot).

    Drains in batches of ``COLD_BOOT_ORPHAN_BATCH_LIMIT`` so large zombie piles do not
    require multiple process restarts.
    """
    from backend.services.paper_service import get_paper_service

    settings = get_settings()
    if not settings.process_watchdog_enabled:
        return []

    older_than = _cold_boot_older_than(now=now)
    paper_service = get_paper_service()
    failed: list[str] = []
    for round_idx in range(COLD_BOOT_ORPHAN_MAX_ROUNDS):
        candidate_ids = await paper_service.list_orphan_pipeline_paper_ids(
            older_than=older_than,
            limit=COLD_BOOT_ORPHAN_BATCH_LIMIT,
        )
        if not candidate_ids:
            break
        for paper_id in candidate_ids:
            try:
                if await paper_service.fail_orphaned_pipeline_paper(
                    paper_id,
                    error_code=PROCESS_ORPHANED_CODE,
                    message=PROCESS_ORPHANED_MESSAGE,
                ):
                    failed.append(paper_id)
            except Exception:
                logger.exception("processing_watchdog_fail_failed", extra={"paper_id": paper_id})
        if len(candidate_ids) < COLD_BOOT_ORPHAN_BATCH_LIMIT:
            break
        if round_idx == COLD_BOOT_ORPHAN_MAX_ROUNDS - 1:
            logger.warning(
                "%s cold_boot orphan drain hit max_rounds=%s healed_so_far=%s",
                PROCESS_WATCHDOG_HEAL_TAG,
                COLD_BOOT_ORPHAN_MAX_ROUNDS,
                len(failed),
                extra={"process_watchdog_heal": True, "failed_count": len(failed)},
            )
    return failed


def _cascade_kill_true_zombie_sync(paper_id: str, *, paper_service: object) -> bool:
    """Cascading Kill Channel for True Zombie (sync / dedicated-thread safe).

    1. Force Cancel Task (inject CancelledError via registry)
    2. Lock / claim eviction (indexing revoke + reextract claim)
    3. Atomic SQL flip → failed + PROCESS_TIMEOUT

    Optionally schedules a full ``abort_in_flight_pipeline`` await on the main loop
    so Task ``finally`` blocks can finish without blocking this thread.
    """
    from backend.services.pipeline_task_registry import (
        abort_in_flight_pipeline,
        force_cancel_paper_work_sync,
    )

    force_cancel_paper_work_sync(paper_id)

    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is not None:
        running.create_task(abort_in_flight_pipeline(paper_id))
    else:
        loop = get_registered_main_event_loop()
        if loop is not None and loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(abort_in_flight_pipeline(paper_id), loop)
            except Exception:
                logger.exception(
                    "processing_watchdog_abort_schedule_failed",
                    extra={"paper_id": paper_id},
                )

    return bool(
        paper_service.fail_orphaned_pipeline_paper_sync(  # type: ignore[attr-defined]
            paper_id,
            error_code=PROCESS_TIMEOUT_CODE,
            message=PROCESS_TIMEOUT_MESSAGE,
        )
    )


async def _cascade_kill_true_zombie_async(paper_id: str, *, paper_service: object) -> bool:
    """Cascading Kill Channel with full await of abort before SQL flip (async path)."""
    from backend.services.pipeline_task_registry import abort_in_flight_pipeline, force_cancel_paper_work_sync

    # Sync inject first so CancelledError is visible even if await is delayed.
    force_cancel_paper_work_sync(paper_id)
    await abort_in_flight_pipeline(paper_id)
    return bool(
        paper_service.fail_orphaned_pipeline_paper_sync(  # type: ignore[attr-defined]
            paper_id,
            error_code=PROCESS_TIMEOUT_CODE,
            message=PROCESS_TIMEOUT_MESSAGE,
        )
    )


def _dispose_or_renew_stuck_processing(
    paper_id: str,
    *,
    paper_service: object,
) -> bool:
    """Dual-check one PROCESSING candidate (sync). Returns True if tombstoned."""
    from backend.services.pipeline_task_registry import is_paper_work_alive

    if is_paper_work_alive(paper_id):
        renewed = paper_service.touch_processing_lease_sync(paper_id)  # type: ignore[attr-defined]
        logger.info(
            PROCESSING_WATCHDOG_LEASE_LOG,
            extra={
                "paper_id": paper_id,
                "renewed": bool(renewed),
                "process_watchdog_heal": True,
                "vitality": "slow_but_alive",
            },
        )
        return False

    return _cascade_kill_true_zombie_sync(paper_id, paper_service=paper_service)


async def _dispose_or_renew_stuck_processing_async(
    paper_id: str,
    *,
    paper_service: object,
) -> bool:
    """Dual-check one PROCESSING candidate (async, full abort drain)."""
    from backend.services.pipeline_task_registry import is_paper_work_alive

    if is_paper_work_alive(paper_id):
        renewed = paper_service.touch_processing_lease_sync(paper_id)  # type: ignore[attr-defined]
        logger.info(
            PROCESSING_WATCHDOG_LEASE_LOG,
            extra={
                "paper_id": paper_id,
                "renewed": bool(renewed),
                "process_watchdog_heal": True,
                "vitality": "slow_but_alive",
            },
        )
        return False

    return await _cascade_kill_true_zombie_async(paper_id, paper_service=paper_service)


async def scan_and_fail_stuck_processing(
    *,
    now: datetime | None = None,
    stuck_after_seconds: float | None = None,
) -> list[str]:
    """Fail PROCESSING papers with stale ``updated_at`` after vitality dual-check + cascade kill."""
    from backend.services.paper_service import get_paper_service

    settings = get_settings()
    if not settings.process_watchdog_enabled:
        return []

    older_than = _process_stuck_older_than(now=now, stuck_after_seconds=stuck_after_seconds)
    paper_service = get_paper_service()
    candidate_ids = paper_service.list_stuck_processing_paper_ids_sync(older_than=older_than)
    failed: list[str] = []
    for paper_id in candidate_ids:
        try:
            if await _dispose_or_renew_stuck_processing_async(paper_id, paper_service=paper_service):
                failed.append(paper_id)
        except Exception:
            logger.exception("processing_watchdog_fail_failed", extra={"paper_id": paper_id})
    return failed


async def scan_and_fail_stuck_pending(
    *,
    now: datetime | None = None,
    stuck_after_seconds: float | None = None,
) -> list[str]:
    """Fail PENDING papers past queue wall-clock (async path) → ``QUEUE_TIMEOUT``."""
    from backend.services.paper_service import get_paper_service

    settings = get_settings()
    if not settings.process_watchdog_enabled:
        return []

    older_than = _pending_stuck_older_than(now=now, stuck_after_seconds=stuck_after_seconds)
    paper_service = get_paper_service()
    candidate_ids = paper_service.list_stuck_pending_paper_ids_sync(older_than=older_than)
    failed: list[str] = []
    for paper_id in candidate_ids:
        try:
            if await paper_service.fail_orphaned_pipeline_paper(
                paper_id,
                error_code=QUEUE_TIMEOUT_CODE,
                message=QUEUE_TIMEOUT_MESSAGE,
            ):
                failed.append(paper_id)
        except Exception:
            logger.exception("processing_watchdog_fail_failed", extra={"paper_id": paper_id})
    return failed


async def reconcile_processing_on_startup() -> list[str]:
    """Cold-boot pass: tombstone only pre-grace pending/processing zombies."""
    settings = get_settings()
    if not settings.process_watchdog_enabled:
        return []
    failed = await scan_and_fail_orphaned_processing()
    if failed:
        logger.warning(
            "%s processing_watchdog_cold_boot_reconcile failed_count=%s paper_ids=%s",
            PROCESS_WATCHDOG_HEAL_TAG,
            len(failed),
            failed,
            extra={
                "failed_count": len(failed),
                "paper_ids": failed,
                "process_watchdog_heal": True,
                "grace_seconds": settings.process_orphan_grace_seconds,
            },
        )
    return failed


def scan_and_fail_stuck_processing_sync(
    *,
    now: datetime | None = None,
    stuck_after_seconds: float | None = None,
    pending_stuck_after_seconds: float | None = None,
) -> list[str]:
    """Sync dual-threshold fail used by the dedicated monitor thread.

    Scans PROCESSING (``PROCESS_TIMEOUT`` after vitality dual-check) and PENDING
    (``QUEUE_TIMEOUT``). Returns the union of failed paper_ids (processing first,
    then pending).
    """
    from backend.services.paper_service import get_paper_service

    settings = get_settings()
    if not settings.process_watchdog_enabled:
        return []

    paper_service = get_paper_service()
    failed: list[str] = []

    processing_cutoff = _process_stuck_older_than(now=now, stuck_after_seconds=stuck_after_seconds)
    for paper_id in paper_service.list_stuck_processing_paper_ids_sync(older_than=processing_cutoff):
        try:
            if _dispose_or_renew_stuck_processing(paper_id, paper_service=paper_service):
                failed.append(paper_id)
        except Exception:
            logger.exception("processing_watchdog_fail_failed", extra={"paper_id": paper_id})

    pending_cutoff = _pending_stuck_older_than(now=now, stuck_after_seconds=pending_stuck_after_seconds)
    for paper_id in paper_service.list_stuck_pending_paper_ids_sync(older_than=pending_cutoff):
        try:
            if paper_service.fail_orphaned_pipeline_paper_sync(
                paper_id,
                error_code=QUEUE_TIMEOUT_CODE,
                message=QUEUE_TIMEOUT_MESSAGE,
            ):
                failed.append(paper_id)
        except Exception:
            logger.exception("processing_watchdog_fail_failed", extra={"paper_id": paper_id})

    return failed


def scan_and_heal_processing_sync(*args, **kwargs):
    """Ops alias; looks up ``scan_and_fail_stuck_processing_sync`` at call time."""
    return scan_and_fail_stuck_processing_sync(*args, **kwargs)


def _watchdog_thread_main() -> None:
    settings = get_settings()
    interval = max(0.05, float(settings.process_watchdog_interval_seconds))
    while not _WATCHDOG_THREAD_STOP.is_set():
        tick_mono = time.monotonic()
        _WATCHDOG_TICK_MONOTONIC.append(tick_mono)
        logger.info(
            PROCESSING_WATCHDOG_TICK_LOG,
            extra={
                "mode": "dedicated_thread",
                "thread_name": PROCESSING_WATCHDOG_THREAD_NAME,
                "monotonic": tick_mono,
                "interval_seconds": interval,
            },
        )
        try:
            healed = scan_and_heal_processing_sync()
            if healed:
                logger.warning(
                    "%s processing_watchdog_wall_clock_heal failed_count=%s paper_ids=%s",
                    PROCESS_WATCHDOG_HEAL_TAG,
                    len(healed),
                    healed,
                    extra={
                        "failed_count": len(healed),
                        "paper_ids": healed,
                        "process_watchdog_heal": True,
                    },
                )
        except Exception:
            logger.exception("processing_watchdog_scan_failed")
        if _WATCHDOG_THREAD_STOP.wait(timeout=interval):
            break


def start_processing_watchdog() -> None:
    """Idempotently start the out-of-loop processing watchdog on a daemon thread."""
    global _WATCHDOG_THREAD

    settings = get_settings()
    if not settings.process_watchdog_enabled:
        return
    with _WATCHDOG_THREAD_LOCK:
        if _WATCHDOG_THREAD is not None and _WATCHDOG_THREAD.is_alive():
            return
        _WATCHDOG_THREAD_STOP.clear()
        _WATCHDOG_THREAD = threading.Thread(
            target=_watchdog_thread_main,
            name=PROCESSING_WATCHDOG_THREAD_NAME,
            daemon=True,
        )
        _WATCHDOG_THREAD.start()
        logger.info(
            "processing_watchdog_started",
            extra={
                "mode": "dedicated_thread",
                "thread_name": PROCESSING_WATCHDOG_THREAD_NAME,
                "interval_seconds": settings.process_watchdog_interval_seconds,
                "stuck_after_seconds": settings.process_watchdog_seconds,
                "pending_queue_timeout_seconds": settings.pending_queue_timeout_seconds,
                "orphan_grace_seconds": settings.process_orphan_grace_seconds,
            },
        )


def stop_processing_watchdog(*, join_timeout_seconds: float = WATCHDOG_THREAD_JOIN_TIMEOUT_SECONDS) -> None:
    """Signal and join the processing watchdog thread (lifespan shutdown)."""
    global _WATCHDOG_THREAD

    with _WATCHDOG_THREAD_LOCK:
        thread = _WATCHDOG_THREAD
        _WATCHDOG_THREAD = None
    if thread is None:
        return
    _WATCHDOG_THREAD_STOP.set()
    thread.join(timeout=join_timeout_seconds)
    if thread.is_alive():
        logger.warning(
            "processing_watchdog_stop_timed_out",
            extra={"join_timeout_seconds": join_timeout_seconds},
        )


def processing_watchdog_thread_is_alive() -> bool:
    """Test helper: whether the dedicated monitor thread is running."""
    thread = _WATCHDOG_THREAD
    return thread is not None and thread.is_alive()


__all__ = [
    "PROCESS_ORPHANED_CODE",
    "PROCESS_ORPHANED_MESSAGE",
    "PROCESS_TIMEOUT_CODE",
    "PROCESS_TIMEOUT_MESSAGE",
    "PROCESS_WATCHDOG_HEAL_TAG",
    "PROCESSING_WATCHDOG_LEASE_LOG",
    "PROCESSING_WATCHDOG_THREAD_NAME",
    "QUEUE_TIMEOUT_CODE",
    "QUEUE_TIMEOUT_MESSAGE",
    "clear_processing_watchdog_tick_timestamps",
    "processing_watchdog_thread_is_alive",
    "processing_watchdog_tick_monotonic_timestamps",
    "reconcile_processing_on_startup",
    "reset_processing_watchdog_sync_engine",
    "scan_and_fail_orphaned_processing",
    "scan_and_fail_stuck_pending",
    "scan_and_fail_stuck_processing",
    "scan_and_fail_stuck_processing_sync",
    "scan_and_heal_processing_sync",
    "start_processing_watchdog",
    "stop_processing_watchdog",
]
