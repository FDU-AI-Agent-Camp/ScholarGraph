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
            return pipeline_row_to_status(run)

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
            if run is None or run.active_rag_run_id is None:
                return None
            return run.active_rag_run_id

    async def set_active_rag_run_id(self, paper_id: str, run_id: str) -> None:
        async with get_async_session_factory()() as session:
            await self._begin_immediate(session)
            run = await session.get(PipelineRunRow, paper_id)
            if run is None:
                msg = f"pipeline run not found: {paper_id}"
                raise KeyError(msg)
            run.active_rag_run_id = run_id if run_id else ""
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

    async def _begin_immediate(self, session: AsyncSession) -> None:
        from sqlalchemy import text

        if session.bind is not None and session.bind.dialect.name == "sqlite":
            await session.execute(text("BEGIN IMMEDIATE"))


@lru_cache
def get_pipeline_repository() -> PipelineRepository:
    return PipelineRepository()
