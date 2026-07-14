"""P13 dual-layer indexing watchdog — macro sweep + cold-boot reconcile."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from backend.config import get_settings
from backend.events.bus import get_event_bus
from backend.events.types import RagIndexed
from backend.schemas.paper import PaperStatus

logger = logging.getLogger(__name__)

RAG_INDEXING_STUCK_WARNING = "rag_indexing_stuck_timeout"
# Structured ops marker for ELK / CloudWatch alert rules (rate spike ⇒ RAG congestion).
P13_WATCHDOG_HEAL_TAG = "[P13_WATCHDOG_HEAL]"
_WATCHDOG_STOP: asyncio.Event | None = None
_WATCHDOG_TASK: asyncio.Task[None] | None = None


async def promote_stuck_indexing_paper(
    paper_id: str,
    *,
    warning_code: str = RAG_INDEXING_STUCK_WARNING,
    message: str | None = None,
) -> bool:
    """Force-promote one indexing paper to ready_with_warnings. Returns whether status changed."""
    from backend.graph.state import STAGE_PERCENT
    from backend.schemas.paper import PaperStatusData, PipelineStage
    from backend.services.paper_service import get_paper_service
    from backend.services.pipeline_status_service import (
        validate_failed_error_fields,
        validate_status_contract,
    )

    paper_service = get_paper_service()
    existing = await paper_service._pipeline_repo.get_latest(paper_id)
    if existing is None or existing.status != PaperStatus.INDEXING:
        return False

    stage = PipelineStage.READY
    percent = STAGE_PERCENT[PipelineStage.READY]
    status = PaperStatus.READY_WITH_WARNINGS
    validate_status_contract(status=status, stage=stage, percent=percent)
    validate_failed_error_fields(status=status, error_code=None, failed_during=None)

    now = datetime.now(UTC)
    merged = list(dict.fromkeys([*existing.extract_warnings, warning_code]))
    snapshot = PaperStatusData(
        paper_id=paper_id,
        status=status,
        percent=percent,
        stage=stage,
        message=message or "建图完成，但向量索引超时未完成（indexing watchdog）；可稍后重试索引或重新抽取",
        updated_at=now,
        preview_available=bool(existing.preview_available),
        error_code=None,
        failed_during=None,
        head_refine_warnings=list(existing.head_refine_warnings),
        classify_warnings=list(existing.classify_warnings),
        extract_warnings=merged,
    )
    await paper_service._pipeline_repo.save_status(paper_id, snapshot)
    get_event_bus().publish_sync(
        RagIndexed(
            paper_id=paper_id,
            success=False,
            terminal_status=PaperStatus.READY_WITH_WARNINGS,
        ),
    )
    logger.warning(
        "%s indexing_watchdog_promoted paper_id=%s warning_code=%s",
        P13_WATCHDOG_HEAL_TAG,
        paper_id,
        warning_code,
        extra={
            "paper_id": paper_id,
            "warning_code": warning_code,
            "p13_watchdog_heal": True,
        },
    )
    return True


async def scan_and_promote_stuck_indexing(
    *,
    now: datetime | None = None,
    stuck_after_seconds: float | None = None,
    heartbeat_stale_seconds: float | None = None,
    force_all: bool = False,
) -> list[str]:
    """Promote stuck INDEXING papers.

    A paper is stuck when:
    - ``indexing_started_at`` is older than ``stuck_after_seconds``, AND
    - ``indexing_heartbeat`` is missing or older than ``heartbeat_stale_seconds``.

    ``force_all`` (cold-boot) ignores age/heartbeat gates — EventBus queues do not survive process restart.
    """
    from backend.repositories.pipeline_repository import get_pipeline_repository

    settings = get_settings()
    if not settings.rag_indexing_watchdog_enabled and not force_all:
        return []

    clock = now or datetime.now(UTC)
    if force_all:
        older_than = None
        heartbeat_stale_before = None
    else:
        stuck_s = stuck_after_seconds if stuck_after_seconds is not None else settings.rag_indexing_watchdog_seconds
        hb_s = (
            heartbeat_stale_seconds
            if heartbeat_stale_seconds is not None
            else settings.rag_indexing_heartbeat_stale_seconds
        )
        older_than = clock - timedelta(seconds=stuck_s)
        heartbeat_stale_before = clock - timedelta(seconds=hb_s)

    candidates = await get_pipeline_repository().list_stuck_indexing_papers(
        older_than=older_than,
        heartbeat_stale_before=heartbeat_stale_before,
    )
    promoted: list[str] = []
    for paper_id, _started, _heartbeat in candidates:
        try:
            if await promote_stuck_indexing_paper(paper_id):
                promoted.append(paper_id)
        except Exception:
            logger.exception("indexing_watchdog_promote_failed", extra={"paper_id": paper_id})
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


async def _watchdog_loop(stop_event: asyncio.Event) -> None:
    settings = get_settings()
    interval = settings.rag_indexing_watchdog_interval_seconds
    while not stop_event.is_set():
        try:
            await scan_and_promote_stuck_indexing()
        except Exception:
            logger.exception("indexing_watchdog_scan_failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            continue


def start_indexing_watchdog() -> None:
    """Idempotently start the lifespan-scoped macro watchdog loop."""
    global _WATCHDOG_STOP, _WATCHDOG_TASK

    settings = get_settings()
    if not settings.rag_indexing_watchdog_enabled:
        return
    if _WATCHDOG_TASK is not None and not _WATCHDOG_TASK.done():
        return
    _WATCHDOG_STOP = asyncio.Event()
    _WATCHDOG_TASK = asyncio.create_task(
        _watchdog_loop(_WATCHDOG_STOP),
        name="rag-indexing-watchdog",
    )
    logger.info(
        "indexing_watchdog_started",
        extra={
            "interval_seconds": settings.rag_indexing_watchdog_interval_seconds,
            "stuck_after_seconds": settings.rag_indexing_watchdog_seconds,
            "heartbeat_stale_seconds": settings.rag_indexing_heartbeat_stale_seconds,
        },
    )


async def stop_indexing_watchdog() -> None:
    """Cancel the macro watchdog loop (lifespan shutdown)."""
    global _WATCHDOG_STOP, _WATCHDOG_TASK

    if _WATCHDOG_STOP is not None:
        _WATCHDOG_STOP.set()
    task = _WATCHDOG_TASK
    _WATCHDOG_TASK = None
    _WATCHDOG_STOP = None
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
