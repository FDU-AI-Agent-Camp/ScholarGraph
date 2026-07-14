"""P13 dual-layer indexing watchdog — macro sweep + cold-boot reconcile.

The macro loop runs on a **dedicated daemon thread** and performs **sync** DB
scans (not ``run_async`` onto the FastAPI loop). ``run_async`` prefers the
registered main loop for worker threads; scheduling scans there would stall the
watchdog whenever false-async code starves that loop. Sync SQLAlchemy keeps
ticks/promote alive independently.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.config import get_settings
from backend.db.models import PaperRow, PipelineRunRow
from backend.events.bus import get_event_bus
from backend.events.types import RagIndexed
from backend.schemas.paper import PaperStatus

logger = logging.getLogger(__name__)

RAG_INDEXING_STUCK_WARNING = "rag_indexing_stuck_timeout"
# Structured ops marker for ELK / CloudWatch alert rules (rate spike ⇒ RAG congestion).
P13_WATCHDOG_HEAL_TAG = "[P13_WATCHDOG_HEAL]"
INDEXING_WATCHDOG_TICK_LOG = "indexing_watchdog_tick"
_WATCHDOG_THREAD_STOP = threading.Event()
_WATCHDOG_THREAD: threading.Thread | None = None
_WATCHDOG_THREAD_LOCK = threading.Lock()
WATCHDOG_THREAD_JOIN_TIMEOUT_SECONDS = 5.0
WATCHDOG_THREAD_NAME = "rag-indexing-watchdog"
_MAX_TICK_TIMESTAMPS = 256
_WATCHDOG_TICK_MONOTONIC: deque[float] = deque(maxlen=_MAX_TICK_TIMESTAMPS)
_SYNC_ENGINE_LOCK = threading.Lock()
_SYNC_ENGINE: Engine | None = None
_SYNC_SESSION_FACTORY: sessionmaker[Session] | None = None
_SYNC_ENGINE_URL: str | None = None


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _get_sync_session_factory() -> sessionmaker[Session]:
    """Sync engine for out-of-loop watchdog scans (recreate when DATABASE_URL changes)."""
    global _SYNC_ENGINE, _SYNC_SESSION_FACTORY, _SYNC_ENGINE_URL

    settings = get_settings()
    url = settings.database_url
    with _SYNC_ENGINE_LOCK:
        if _SYNC_SESSION_FACTORY is not None and _SYNC_ENGINE_URL == url:
            return _SYNC_SESSION_FACTORY
        if _SYNC_ENGINE is not None:
            _SYNC_ENGINE.dispose()
        _SYNC_ENGINE = create_engine(url, future=True, pool_pre_ping=True)
        _SYNC_SESSION_FACTORY = sessionmaker(bind=_SYNC_ENGINE, expire_on_commit=False, class_=Session)
        _SYNC_ENGINE_URL = url
        return _SYNC_SESSION_FACTORY


def reset_watchdog_sync_engine() -> None:
    """Test helper: drop cached sync engine after DATABASE_URL changes."""
    global _SYNC_ENGINE, _SYNC_SESSION_FACTORY, _SYNC_ENGINE_URL

    with _SYNC_ENGINE_LOCK:
        engine = _SYNC_ENGINE
        _SYNC_ENGINE = None
        _SYNC_SESSION_FACTORY = None
        _SYNC_ENGINE_URL = None
    if engine is not None:
        engine.dispose()


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


def promote_stuck_indexing_paper_sync(
    paper_id: str,
    *,
    warning_code: str = RAG_INDEXING_STUCK_WARNING,
    message: str | None = None,
) -> bool:
    """Sync promote for the dedicated watchdog thread (main-loop starvation safe)."""
    from backend.graph.state import STAGE_PERCENT
    from backend.schemas.paper import PipelineStage
    from backend.services.pipeline_status_service import (
        validate_failed_error_fields,
        validate_status_contract,
    )

    factory = _get_sync_session_factory()
    with factory() as db:
        paper = db.get(PaperRow, paper_id)
        run = db.get(PipelineRunRow, paper_id)
        if paper is None or run is None or paper.status != PaperStatus.INDEXING.value:
            return False

        stage = PipelineStage.READY
        percent = STAGE_PERCENT[PipelineStage.READY]
        status = PaperStatus.READY_WITH_WARNINGS
        validate_status_contract(status=status, stage=stage, percent=percent)
        validate_failed_error_fields(status=status, error_code=None, failed_during=None)

        now = datetime.now(UTC)
        prior_warnings: list[str] = [str(item) for item in (run.extract_warnings or [])]
        merged_warnings: list[str] = list(dict.fromkeys([*prior_warnings, warning_code]))
        run.stage = stage.value
        run.percent = percent
        run.message = message or "建图完成，但向量索引超时未完成（indexing watchdog）；可稍后重试索引或重新抽取"
        run.error_code = None
        run.failed_during = None
        run.extract_warnings = merged_warnings
        run.indexing_started_at = None
        run.indexing_heartbeat = None
        run.updated_at = now
        paper.status = status.value
        paper.updated_at = now
        db.commit()

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

    factory = _get_sync_session_factory()
    candidate_ids: list[str] = []
    with factory() as session:
        stmt = (
            select(PipelineRunRow)
            .join(PaperRow, PaperRow.paper_id == PipelineRunRow.paper_id)
            .where(PaperRow.status == PaperStatus.INDEXING.value)
            .order_by(PipelineRunRow.updated_at.asc())
            .limit(200)
        )
        rows = list(session.scalars(stmt).all())
        for run in rows:
            started = run.indexing_started_at or run.updated_at
            if older_than is not None and started is not None:
                if _as_utc(started) >= _as_utc(older_than):
                    continue
            heartbeat = run.indexing_heartbeat
            if heartbeat_stale_before is not None and heartbeat is not None:
                if _as_utc(heartbeat) >= _as_utc(heartbeat_stale_before):
                    continue
            candidate_ids.append(run.paper_id)

    promoted: list[str] = []
    for paper_id in candidate_ids:
        try:
            if promote_stuck_indexing_paper_sync(paper_id):
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
        # Interruptible sleep so shutdown does not wait a full interval.
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
        thread = threading.Thread(
            target=_watchdog_thread_main,
            name=WATCHDOG_THREAD_NAME,
            daemon=True,
        )
        _WATCHDOG_THREAD = thread
        thread.start()
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
    _WATCHDOG_THREAD_STOP.set()
    if thread is None or not thread.is_alive():
        return
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
