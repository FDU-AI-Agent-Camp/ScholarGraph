"""Sync SQLAlchemy helpers for out-of-loop indexing watchdog (P13).

Used only from the dedicated watchdog OS thread / PaperService sync promote path.
Must not schedule work onto the FastAPI asyncio loop.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.config import get_settings
from backend.db.models import PaperRow, PipelineRunRow
from backend.schemas.paper import PaperStatus

_SYNC_ENGINE_LOCK = threading.Lock()
_SYNC_ENGINE: Engine | None = None
_SYNC_SESSION_FACTORY: sessionmaker[Session] | None = None
_SYNC_ENGINE_URL: str | None = None


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def get_pipeline_sync_session_factory() -> sessionmaker[Session]:
    """Return a process-wide sync sessionmaker (recreate when DATABASE_URL changes)."""
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


def reset_pipeline_sync_engine() -> None:
    """Test helper: drop cached sync engine after DATABASE_URL changes."""
    global _SYNC_ENGINE, _SYNC_SESSION_FACTORY, _SYNC_ENGINE_URL

    with _SYNC_ENGINE_LOCK:
        engine = _SYNC_ENGINE
        _SYNC_ENGINE = None
        _SYNC_SESSION_FACTORY = None
        _SYNC_ENGINE_URL = None
    if engine is not None:
        engine.dispose()


def promote_stuck_indexing_row_sync(
    paper_id: str,
    *,
    warning_code: str,
    message: str,
) -> bool:
    """Force INDEXING → ready_with_warnings via sync SQL. Returns whether status changed."""
    from backend.graph.state import STAGE_PERCENT
    from backend.schemas.paper import PipelineStage
    from backend.services.pipeline_status_service import (
        validate_failed_error_fields,
        validate_status_contract,
    )

    factory = get_pipeline_sync_session_factory()
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
        run.message = message
        run.error_code = None
        run.failed_during = None
        run.extract_warnings = merged_warnings
        run.indexing_started_at = None
        run.indexing_heartbeat = None
        run.updated_at = now
        paper.status = status.value
        paper.updated_at = now
        db.commit()
    return True


def list_stuck_indexing_paper_ids_sync(
    *,
    older_than: datetime | None = None,
    heartbeat_stale_before: datetime | None = None,
    limit: int = 200,
) -> list[str]:
    """Return paper_ids for stuck INDEXING rows (sync, main-loop independent)."""
    factory = get_pipeline_sync_session_factory()
    candidate_ids: list[str] = []
    with factory() as session:
        stmt = (
            select(PipelineRunRow)
            .join(PaperRow, PaperRow.paper_id == PipelineRunRow.paper_id)
            .where(PaperRow.status == PaperStatus.INDEXING.value)
            .order_by(PipelineRunRow.updated_at.asc())
            .limit(limit)
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
    return candidate_ids


def stuck_bounds_from_settings(
    *,
    now: datetime | None = None,
    stuck_after_seconds: float | None = None,
    heartbeat_stale_seconds: float | None = None,
    force_all: bool = False,
) -> tuple[datetime | None, datetime | None]:
    """Compute ``(older_than, heartbeat_stale_before)`` for stuck scans."""
    settings = get_settings()
    clock = now or datetime.now(UTC)
    if force_all:
        return None, None
    stuck_s = stuck_after_seconds if stuck_after_seconds is not None else settings.rag_indexing_watchdog_seconds
    hb_s = (
        heartbeat_stale_seconds
        if heartbeat_stale_seconds is not None
        else settings.rag_indexing_heartbeat_stale_seconds
    )
    return clock - timedelta(seconds=stuck_s), clock - timedelta(seconds=hb_s)


_ORPHAN_PIPELINE_STATUSES = frozenset(
    {PaperStatus.PENDING.value, PaperStatus.PROCESSING.value},
)


def list_orphan_pipeline_paper_ids_sync(*, limit: int = 200) -> list[str]:
    """Return paper_ids stuck in pending/processing (cold-boot tombstone scan)."""
    factory = get_pipeline_sync_session_factory()
    with factory() as session:
        stmt = (
            select(PaperRow.paper_id)
            .where(PaperRow.status.in_(tuple(_ORPHAN_PIPELINE_STATUSES)))
            .order_by(PaperRow.updated_at.asc())
            .limit(limit)
        )
        return list(session.scalars(stmt).all())


def list_stuck_processing_paper_ids_sync(
    *,
    older_than: datetime,
    limit: int = 200,
) -> list[str]:
    """Return PROCESSING paper_ids whose run/paper ``updated_at`` is older than *older_than*."""
    factory = get_pipeline_sync_session_factory()
    candidate_ids: list[str] = []
    cutoff = _as_utc(older_than)
    with factory() as session:
        stmt = (
            select(PipelineRunRow, PaperRow)
            .join(PaperRow, PaperRow.paper_id == PipelineRunRow.paper_id)
            .where(PaperRow.status == PaperStatus.PROCESSING.value)
            .order_by(PipelineRunRow.updated_at.asc())
            .limit(limit)
        )
        for run, paper in session.execute(stmt).all():
            stamp = run.updated_at or paper.updated_at
            if stamp is None:
                candidate_ids.append(run.paper_id)
                continue
            if _as_utc(stamp) < cutoff:
                candidate_ids.append(run.paper_id)
    return candidate_ids


def fail_orphaned_pipeline_row_sync(
    paper_id: str,
    *,
    error_code: str,
    message: str,
) -> bool:
    """Force pending/processing → failed via sync SQL. Returns whether status changed."""
    from backend.graph.state import STAGE_PERCENT
    from backend.schemas.paper import PipelineStage
    from backend.services.pipeline_status_service import (
        PROCESSING_STAGES,
        validate_failed_error_fields,
        validate_status_contract,
    )

    factory = get_pipeline_sync_session_factory()
    with factory() as db:
        paper = db.get(PaperRow, paper_id)
        run = db.get(PipelineRunRow, paper_id)
        if paper is None or run is None:
            return False
        if paper.status not in _ORPHAN_PIPELINE_STATUSES:
            return False

        failed_during_value: str | None = None
        if run.stage:
            try:
                stage_enum = PipelineStage(run.stage)
            except ValueError:
                stage_enum = None
            if stage_enum is not None and stage_enum in PROCESSING_STAGES:
                failed_during_value = stage_enum.value

        stage = PipelineStage.FAILED
        percent = STAGE_PERCENT[PipelineStage.FAILED]
        status = PaperStatus.FAILED
        validate_status_contract(status=status, stage=stage, percent=percent)
        validate_failed_error_fields(
            status=status,
            error_code=error_code,
            failed_during=PipelineStage(failed_during_value) if failed_during_value else None,
        )

        now = datetime.now(UTC)
        run.stage = stage.value
        run.percent = percent
        run.message = message
        run.error_code = error_code
        run.failed_during = failed_during_value
        run.updated_at = now
        paper.status = status.value
        paper.updated_at = now
        db.commit()
    return True
