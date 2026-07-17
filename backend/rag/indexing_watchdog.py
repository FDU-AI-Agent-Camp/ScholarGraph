# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""P13 dual-layer indexing watchdog — macro sweep + cold-boot reconcile.

The macro loop runs on a **dedicated daemon thread** and performs **sync** DB
scans (not ``run_async`` onto the FastAPI loop). Promote semantics live on
``PaperService`` (``promote_stuck_indexing_paper[_sync]``); this module only
schedules and orchestrates.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import datetime

from backend.config import get_settings
from backend.repositories.pipeline_sync import (
    reset_pipeline_sync_engine,
    stuck_bounds_from_settings,
)
from backend.services.paper_pipeline_ops import (
    P13_WATCHDOG_HEAL_TAG,
    RAG_INDEXING_STUCK_WARNING,
)

logger = logging.getLogger(__name__)

INDEXING_WATCHDOG_TICK_LOG = "indexing_watchdog_tick"
_WATCHDOG_THREAD_STOP = threading.Event()
_WATCHDOG_THREAD: threading.Thread | None = None
_WATCHDOG_THREAD_LOCK = threading.Lock()
WATCHDOG_THREAD_JOIN_TIMEOUT_SECONDS = 5.0
WATCHDOG_THREAD_NAME = "rag-indexing-watchdog"
_MAX_TICK_TIMESTAMPS = 256
_WATCHDOG_TICK_MONOTONIC: deque[float] = deque(maxlen=_MAX_TICK_TIMESTAMPS)
COLD_BOOT_INDEXING_BATCH_LIMIT = 200
COLD_BOOT_INDEXING_MAX_ROUNDS = 50


def reset_watchdog_sync_engine() -> None:
    """Test helper: drop cached sync engine after DATABASE_URL changes."""
    reset_pipeline_sync_engine()


def watchdog_tick_monotonic_timestamps() -> list[float]:
    """Test helper: monotonic timestamps of dedicated-thread ticks."""
    return list(_WATCHDOG_TICK_MONOTONIC)


def clear_watchdog_tick_timestamps() -> None:
    """Test helper: reset recorded tick timestamps."""
    _WATCHDOG_TICK_MONOTONIC.clear()


async def promote_stuck_indexing_paper(
    paper_id: str,
    *,
    warning_code: str = RAG_INDEXING_STUCK_WARNING,
    message: str | None = None,
) -> bool:
    """Force-promote one indexing paper via PaperService facade."""
    from backend.services.paper_service import get_paper_service

    return await get_paper_service().promote_stuck_indexing_paper(
        paper_id,
        warning_code=warning_code,
        message=message,
    )


async def scan_and_promote_stuck_indexing(
    *,
    now: datetime | None = None,
    stuck_after_seconds: float | None = None,
    heartbeat_stale_seconds: float | None = None,
    force_all: bool = False,
) -> list[str]:
    """Promote stuck INDEXING papers (async path; cold-boot uses ``force_all``).

    When ``force_all`` (cold-boot), drain in 200-row rounds so large piles need one boot.
    """
    from backend.services.paper_service import get_paper_service

    settings = get_settings()
    if not settings.rag_indexing_watchdog_enabled and not force_all:
        return []

    older_than, heartbeat_stale_before = stuck_bounds_from_settings(
        now=now,
        stuck_after_seconds=stuck_after_seconds,
        heartbeat_stale_seconds=heartbeat_stale_seconds,
        force_all=force_all,
    )
    paper_service = get_paper_service()
    promoted: list[str] = []
    max_rounds = COLD_BOOT_INDEXING_MAX_ROUNDS if force_all else 1
    for round_idx in range(max_rounds):
        candidates = await paper_service.list_stuck_indexing_papers(
            older_than=older_than,
            heartbeat_stale_before=heartbeat_stale_before,
            limit=COLD_BOOT_INDEXING_BATCH_LIMIT,
        )
        if not candidates:
            break
        for paper_id, _started, _heartbeat in candidates:
            try:
                if await paper_service.promote_stuck_indexing_paper(paper_id):
                    promoted.append(paper_id)
            except Exception:
                logger.exception("indexing_watchdog_promote_failed", extra={"paper_id": paper_id})
        if len(candidates) < COLD_BOOT_INDEXING_BATCH_LIMIT:
            break
        if force_all and round_idx == COLD_BOOT_INDEXING_MAX_ROUNDS - 1:
            logger.warning(
                "%s cold_boot indexing drain hit max_rounds=%s promoted_so_far=%s",
                P13_WATCHDOG_HEAL_TAG,
                COLD_BOOT_INDEXING_MAX_ROUNDS,
                len(promoted),
                extra={"p13_watchdog_heal": True, "promoted_count": len(promoted)},
            )
    return promoted


async def reconcile_indexing_on_startup() -> list[str]:
    """Cold-boot pass: any leftover INDEXING row is orphaned (in-memory EventBus empty)."""
    settings = get_settings()
    if not settings.rag_indexing_watchdog_enabled:
        return []
    promoted = await scan_and_promote_stuck_indexing(force_all=True)
    if promoted:
        logger.warning(
            "%s indexing_watchdog_cold_boot_reconcile promoted_count=%s paper_ids=%s",
            P13_WATCHDOG_HEAL_TAG,
            len(promoted),
            promoted,
            extra={
                "promoted_count": len(promoted),
                "paper_ids": promoted,
                "p13_watchdog_heal": True,
            },
        )
    return promoted


def promote_stuck_indexing_paper_sync(
    paper_id: str,
    *,
    warning_code: str = RAG_INDEXING_STUCK_WARNING,
    message: str | None = None,
) -> bool:
    """Sync promote for the dedicated watchdog thread (main-loop starvation safe)."""
    from backend.services.paper_service import get_paper_service

    return get_paper_service().promote_stuck_indexing_paper_sync(
        paper_id,
        warning_code=warning_code,
        message=message,
    )


def scan_and_promote_stuck_indexing_sync(
    *,
    now: datetime | None = None,
    stuck_after_seconds: float | None = None,
    heartbeat_stale_seconds: float | None = None,
    force_all: bool = False,
) -> list[str]:
    """Sync stuck-INDEXING promote used by the dedicated monitor thread.

    Must not call ``run_async`` / the FastAPI loop — main-loop starvation must not
    block ticks or heals.
    """
    from backend.services.paper_service import get_paper_service

    settings = get_settings()
    if not settings.rag_indexing_watchdog_enabled and not force_all:
        return []

    older_than, heartbeat_stale_before = stuck_bounds_from_settings(
        now=now,
        stuck_after_seconds=stuck_after_seconds,
        heartbeat_stale_seconds=heartbeat_stale_seconds,
        force_all=force_all,
    )
    paper_service = get_paper_service()
    candidate_ids = paper_service.list_stuck_indexing_paper_ids_sync(
        older_than=older_than,
        heartbeat_stale_before=heartbeat_stale_before,
    )
    promoted: list[str] = []
    for paper_id in candidate_ids:
        try:
            if paper_service.promote_stuck_indexing_paper_sync(paper_id):
                promoted.append(paper_id)
        except Exception:
            logger.exception("indexing_watchdog_promote_failed", extra={"paper_id": paper_id})
    return promoted


def _watchdog_thread_main() -> None:
    """OS thread body: tick log → sync scan → interruptible sleep (never main loop)."""
    settings = get_settings()
    interval = max(0.05, float(settings.rag_indexing_watchdog_interval_seconds))
    while not _WATCHDOG_THREAD_STOP.is_set():
        tick_mono = time.monotonic()
        _WATCHDOG_TICK_MONOTONIC.append(tick_mono)
        logger.info(
            INDEXING_WATCHDOG_TICK_LOG,
            extra={
                "mode": "dedicated_thread",
                "thread_name": WATCHDOG_THREAD_NAME,
                "monotonic": tick_mono,
                "interval_seconds": interval,
            },
        )
        try:
            scan_and_promote_stuck_indexing_sync()
        except Exception:
            logger.exception("indexing_watchdog_scan_failed")
        if _WATCHDOG_THREAD_STOP.wait(timeout=interval):
            break


def start_indexing_watchdog() -> None:
    """Idempotently start the out-of-loop macro watchdog on a daemon thread."""
    global _WATCHDOG_THREAD

    settings = get_settings()
    if not settings.rag_indexing_watchdog_enabled:
        return
    with _WATCHDOG_THREAD_LOCK:
        if _WATCHDOG_THREAD is not None and _WATCHDOG_THREAD.is_alive():
            return
        _WATCHDOG_THREAD_STOP.clear()
        _WATCHDOG_THREAD = threading.Thread(
            target=_watchdog_thread_main,
            name=WATCHDOG_THREAD_NAME,
            daemon=True,
        )
        _WATCHDOG_THREAD.start()
        logger.info(
            "indexing_watchdog_started",
            extra={
                "mode": "dedicated_thread",
                "thread_name": WATCHDOG_THREAD_NAME,
                "interval_seconds": settings.rag_indexing_watchdog_interval_seconds,
                "stuck_after_seconds": settings.rag_indexing_watchdog_seconds,
                "heartbeat_stale_seconds": settings.rag_indexing_heartbeat_stale_seconds,
            },
        )


def stop_indexing_watchdog(*, join_timeout_seconds: float = WATCHDOG_THREAD_JOIN_TIMEOUT_SECONDS) -> None:
    """Signal and join the macro watchdog thread (lifespan shutdown)."""
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
            "indexing_watchdog_stop_timed_out",
            extra={"join_timeout_seconds": join_timeout_seconds},
        )


def watchdog_thread_is_alive() -> bool:
    """Test helper: whether the dedicated monitor thread is running."""
    thread = _WATCHDOG_THREAD
    return thread is not None and thread.is_alive()


__all__ = [
    "INDEXING_WATCHDOG_TICK_LOG",
    "P13_WATCHDOG_HEAL_TAG",
    "RAG_INDEXING_STUCK_WARNING",
    "WATCHDOG_THREAD_NAME",
    "clear_watchdog_tick_timestamps",
    "promote_stuck_indexing_paper",
    "promote_stuck_indexing_paper_sync",
    "reconcile_indexing_on_startup",
    "reset_watchdog_sync_engine",
    "scan_and_promote_stuck_indexing",
    "scan_and_promote_stuck_indexing_sync",
    "start_indexing_watchdog",
    "stop_indexing_watchdog",
    "watchdog_thread_is_alive",
    "watchdog_tick_monotonic_timestamps",
]
