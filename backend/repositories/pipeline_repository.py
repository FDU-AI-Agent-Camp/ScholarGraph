"""UPSERT and warning-append semantics for ``pipeline_runs``."""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.db.base import get_async_session_factory
from backend.db.models import PaperRow, PipelineRunRow
from backend.repositories.mappers import pipeline_row_to_status
from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.paper import PaperStatus, PaperStatusData


def _merge_warning_codes(existing: list[str] | None, incoming: list[str]) -> list[str]:
    return list(dict.fromkeys([*(existing or []), *incoming]))


def _resolve_indexing_timestamps(
    *,
    existing_started_at: datetime | None,
    existing_heartbeat: datetime | None,
    status: PaperStatus,
    now: datetime,
) -> tuple[datetime | None, datetime | None]:
    """Wall-clock checkpoint + initial heartbeat on enter INDEXING; clear on leave."""
    if status == PaperStatus.INDEXING:
        started = existing_started_at or now
        # First enter sets a pulse; later save_status calls preserve the last heartbeat.
        heartbeat = existing_heartbeat or now
        return started, heartbeat
    return None, None


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class PipelineRepository:
    """Latest pipeline snapshot per paper (one row per paper_id)."""

    async def save_status(self, paper_id: str, data: PaperStatusData) -> None:
        async with get_async_session_factory()() as session:
            await self._begin_immediate(session)
            paper = await session.get(PaperRow, paper_id)
            if paper is None:
                msg = f"paper not found: {paper_id}"
                raise KeyError(msg)

            run = await session.get(PipelineRunRow, paper_id)
            now = datetime.now(UTC)
            indexing_started_at, indexing_heartbeat = _resolve_indexing_timestamps(
                existing_started_at=None if run is None else run.indexing_started_at,
                existing_heartbeat=None if run is None else run.indexing_heartbeat,
                status=data.status,
                now=now,
            )
            if run is None:
                run = PipelineRunRow(
                    paper_id=paper_id,
                    stage=data.stage.value if data.stage is not None else None,
                    percent=data.percent,
                    message=data.message,
                    error_code=data.error_code,
                    failed_during=data.failed_during.value if data.failed_during is not None else None,
                    head_refine_warnings=list(data.head_refine_warnings),
                    classify_warnings=list(data.classify_warnings),
                    extract_warnings=list(data.extract_warnings),
                    active_rag_run_id=None,
                    preview_graph=None,
                    indexing_started_at=indexing_started_at,
                    indexing_heartbeat=indexing_heartbeat,
                    created_at=now,
                    updated_at=now,
                )
                session.add(run)
            else:
                run.stage = data.stage.value if data.stage is not None else None
                run.percent = data.percent
                run.message = data.message
                run.error_code = data.error_code
                run.failed_during = data.failed_during.value if data.failed_during is not None else None
                run.head_refine_warnings = list(data.head_refine_warnings)
                run.classify_warnings = list(data.classify_warnings)
                run.extract_warnings = list(data.extract_warnings)
                run.indexing_started_at = indexing_started_at
                run.indexing_heartbeat = indexing_heartbeat
                run.updated_at = now

            paper.status = data.status.value
            paper.preview_available = data.preview_available
            paper.updated_at = now
            await session.commit()

    async def get_latest(self, paper_id: str) -> PaperStatusData | None:
        async with get_async_session_factory()() as session:
            stmt = (
                select(PipelineRunRow)
                .where(PipelineRunRow.paper_id == paper_id)
                .options(selectinload(PipelineRunRow.paper))
            )
            run = (await session.scalars(stmt)).first()
            if run is None:
                return None
            snapshot = pipeline_row_to_status(run)
            from backend.services.status_snapshot_guard import audit_dual_table_invariant

            audit_dual_table_invariant(snapshot)
            return snapshot

    async def record_warnings(
        self,
        paper_id: str,
        *,
        head_refine: list[str] | None = None,
        classify: list[str] | None = None,
        extract: list[str] | None = None,
    ) -> None:
        if not head_refine and not classify and not extract:
            return

        async with get_async_session_factory()() as session:
            await self._begin_immediate(session)
            run = await session.get(PipelineRunRow, paper_id, with_for_update=True)
            if run is None:
                msg = f"pipeline run not found: {paper_id}"
                raise KeyError(msg)

            if head_refine:
                run.head_refine_warnings = _merge_warning_codes(run.head_refine_warnings, head_refine)
            if classify:
                run.classify_warnings = _merge_warning_codes(run.classify_warnings, classify)
            if extract:
                run.extract_warnings = _merge_warning_codes(run.extract_warnings, extract)
            run.updated_at = datetime.now(UTC)
            await session.commit()

    async def get_active_rag_run_id(self, paper_id: str) -> str | None:
        async with get_async_session_factory()() as session:
            run = await session.get(PipelineRunRow, paper_id)
            if run is None:
                return None
            value = run.active_rag_run_id
            # Treat legacy empty-string clears as unset (column is nullable).
            if value is None or value == "":
                return None
            return value

    async def set_active_rag_run_id(self, paper_id: str, run_id: str | None) -> None:
        """Set the active RAG run id, or clear it (``None`` / ``""`` → SQL NULL)."""
        async with get_async_session_factory()() as session:
            await self._begin_immediate(session)
            run = await session.get(PipelineRunRow, paper_id)
            if run is None:
                msg = f"pipeline run not found: {paper_id}"
                raise KeyError(msg)
            run.active_rag_run_id = run_id if run_id else None
            run.updated_at = datetime.now(UTC)
            await session.commit()

    async def save_preview_graph(self, paper_id: str, graph: UnifiedPaperGraph) -> None:
        """Persist preview graph via full JSON replacement (never in-place JSON mutation)."""
        payload = graph.model_dump(mode="json")
        async with get_async_session_factory()() as session:
            await self._begin_immediate(session)
            run = await session.get(PipelineRunRow, paper_id)
            if run is None:
                msg = f"pipeline run not found: {paper_id}"
                raise KeyError(msg)
            run.preview_graph = payload
            run.updated_at = datetime.now(UTC)
            await session.commit()

    async def get_preview_graph(self, paper_id: str) -> UnifiedPaperGraph | None:
        async with get_async_session_factory()() as session:
            run = await session.get(PipelineRunRow, paper_id)
            if run is None or run.preview_graph is None:
                return None
            return UnifiedPaperGraph.model_validate(run.preview_graph)

    async def clear_preview_graph(self, paper_id: str) -> None:
        async with get_async_session_factory()() as session:
            await self._begin_immediate(session)
            run = await session.get(PipelineRunRow, paper_id)
            if run is None:
                return
            run.preview_graph = None
            run.updated_at = datetime.now(UTC)
            await session.commit()

    async def clear_ephemeral_pipeline_state(self, paper_id: str) -> None:
        """Clear preview graph and RAG run tracking for re-extract or finalize."""
        async with get_async_session_factory()() as session:
            await self._begin_immediate(session)
            run = await session.get(PipelineRunRow, paper_id)
            if run is None:
                return
            run.preview_graph = None
            run.active_rag_run_id = None
            run.updated_at = datetime.now(UTC)
            await session.commit()

    async def reset_for_reextract(self, paper_id: str, *, message: str) -> PaperStatusData:
        """Reset pipeline snapshot to pending and clear warnings/error fields."""
        now = datetime.now(UTC)
        snapshot = PaperStatusData(
            paper_id=paper_id,
            status=PaperStatus.PENDING,
            percent=0,
            stage=None,
            message=message,
            updated_at=now,
            preview_available=False,
            error_code=None,
            failed_during=None,
            head_refine_warnings=[],
            classify_warnings=[],
            extract_warnings=[],
        )
        await self.save_status(paper_id, snapshot)
        await self.clear_ephemeral_pipeline_state(paper_id)
        return snapshot

    async def touch_indexing_heartbeat(self, paper_id: str, *, at: datetime | None = None) -> bool:
        """Refresh ``indexing_heartbeat`` while the paper remains in INDEXING."""
        async with get_async_session_factory()() as session:
            await self._begin_immediate(session)
            paper = await session.get(PaperRow, paper_id)
            run = await session.get(PipelineRunRow, paper_id)
            if paper is None or run is None:
                return False
            if paper.status != PaperStatus.INDEXING.value:
                return False
            pulse = at or datetime.now(UTC)
            run.indexing_heartbeat = pulse
            run.updated_at = pulse
            paper.updated_at = pulse
            await session.commit()
            return True

    async def list_stuck_indexing_papers(
        self,
        *,
        older_than: datetime | None = None,
        heartbeat_stale_before: datetime | None = None,
        limit: int = 200,
    ) -> list[tuple[str, datetime | None, datetime | None]]:
        """Return ``(paper_id, indexing_started_at, indexing_heartbeat)`` for stuck INDEXING rows.

        When ``older_than`` is set, only rows whose start checkpoint is strictly before
        that instant are returned. When ``heartbeat_stale_before`` is set, rows with a
        fresher heartbeat are excluded (active long-running indexors).
        """
        async with get_async_session_factory()() as session:
            stmt = (
                select(PipelineRunRow)
                .join(PaperRow, PaperRow.paper_id == PipelineRunRow.paper_id)
                .where(PaperRow.status == PaperStatus.INDEXING.value)
                .order_by(PipelineRunRow.updated_at.asc())
                .limit(limit)
            )
            rows = list((await session.scalars(stmt)).all())
            out: list[tuple[str, datetime | None, datetime | None]] = []
            for run in rows:
                started = run.indexing_started_at or run.updated_at
                if older_than is not None and started is not None:
                    if _as_utc(started) >= _as_utc(older_than):
                        continue
                heartbeat = run.indexing_heartbeat
                if heartbeat_stale_before is not None and heartbeat is not None:
                    if _as_utc(heartbeat) >= _as_utc(heartbeat_stale_before):
                        continue
                out.append((run.paper_id, run.indexing_started_at, run.indexing_heartbeat))
            return out

    async def delete_run(self, paper_id: str) -> bool:
        """Delete the pipeline snapshot row for a paper (test teardown / compat shim)."""
        async with get_async_session_factory()() as session:
            await self._begin_immediate(session)
            run = await session.get(PipelineRunRow, paper_id)
            if run is None:
                return False
            await session.delete(run)
            await session.commit()
            return True

    async def _begin_immediate(self, session: AsyncSession) -> None:
        from sqlalchemy import text

        if session.bind is not None and session.bind.dialect.name == "sqlite":
            await session.execute(text("BEGIN IMMEDIATE"))


@lru_cache
def get_pipeline_repository() -> PipelineRepository:
    return PipelineRepository()
