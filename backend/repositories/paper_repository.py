"""CRUD for the ``papers`` table."""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.base import get_async_session_factory
from backend.db.models import DEFAULT_EXTRACTOR_CONFIG_HASH, DEFAULT_GRAPH_VERSION, PaperRow
from backend.repositories.mappers import paper_row_to_detail, paper_row_to_summary
from backend.schemas.paper import PaperDetail, PaperStatus, PaperSummary
from backend.schemas.paradigm import Paradigm, ParadigmClassification


def _bump_graph_version(current: str) -> str:
    try:
        return str(int(current) + 1)
    except ValueError:
        return "2"


class PaperRepository:
    """Persistence access for paper metadata rows."""

    async def create(
        self,
        paper_id: str,
        title: str,
        pdf_path: str,
        *,
        status: PaperStatus = PaperStatus.PENDING,
    ) -> PaperDetail:
        now = datetime.now(UTC)
        async with get_async_session_factory()() as session:
            await self._begin_immediate(session)
            row = PaperRow(
                paper_id=paper_id,
                title=title,
                pdf_path=pdf_path,
                status=status.value,
                graph_version=DEFAULT_GRAPH_VERSION,
                extractor_config_hash=DEFAULT_EXTRACTOR_CONFIG_HASH,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return paper_row_to_detail(row)

    async def get(self, paper_id: str) -> PaperDetail | None:
        async with get_async_session_factory()() as session:
            row = await session.get(PaperRow, paper_id)
            if row is None:
                return None
            return paper_row_to_detail(row)

    async def list(
        self,
        *,
        paradigm: Paradigm | None = None,
        status: PaperStatus | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[PaperSummary], int]:
        async with get_async_session_factory()() as session:
            filters = []
            if paradigm is not None:
                filters.append(PaperRow.paradigm == paradigm.value)
            if status is not None:
                filters.append(PaperRow.status == status.value)

            count_stmt = select(func.count()).select_from(PaperRow)
            if filters:
                count_stmt = count_stmt.where(*filters)
            total = int((await session.scalar(count_stmt)) or 0)

            stmt = select(PaperRow).order_by(PaperRow.created_at.desc())
            if filters:
                stmt = stmt.where(*filters)
            stmt = stmt.offset(offset).limit(limit)
            rows = (await session.scalars(stmt)).all()
            return [paper_row_to_summary(row) for row in rows], total

    async def is_empty(self) -> bool:
        async with get_async_session_factory()() as session:
            total = await session.scalar(select(func.count()).select_from(PaperRow))
            return int(total or 0) == 0

    async def update_status(
        self,
        paper_id: str,
        *,
        status: PaperStatus,
    ) -> None:
        """Update paper + pipeline snapshot atomically (never papers-only)."""
        from backend.graph.state import STAGE_PERCENT
        from backend.repositories.pipeline_repository import get_pipeline_repository
        from backend.schemas.paper import PaperStatusData, PipelineStage
        from backend.services.pipeline_status_service import PROCESSING_STAGES

        pipeline_repo = get_pipeline_repository()
        latest = await pipeline_repo.get_latest(paper_id)
        if latest is None:
            msg = f"pipeline run not found: {paper_id}"
            raise KeyError(msg)

        stage: PipelineStage | None
        percent: int
        if status == PaperStatus.READY:
            stage = PipelineStage.READY
            percent = STAGE_PERCENT[PipelineStage.READY]
        elif status == PaperStatus.READY_WITH_WARNINGS:
            stage = PipelineStage.READY
            percent = STAGE_PERCENT[PipelineStage.READY]
        elif status == PaperStatus.INDEXING:
            stage = PipelineStage.INDEXING
            percent = STAGE_PERCENT[PipelineStage.INDEXING]
        elif status == PaperStatus.FAILED:
            stage = PipelineStage.FAILED
            percent = STAGE_PERCENT[PipelineStage.FAILED]
        elif status == PaperStatus.PENDING:
            stage = None
            percent = 0
        else:
            stage = (
                latest.stage
                if latest.stage is not None and latest.stage in PROCESSING_STAGES
                else PipelineStage.INGESTING
            )
            percent = STAGE_PERCENT[stage]

        snapshot = PaperStatusData(
            paper_id=paper_id,
            status=status,
            percent=percent,
            stage=stage,
            message=latest.message,
            updated_at=datetime.now(UTC),
            preview_available=latest.preview_available,
            error_code=latest.error_code if status == PaperStatus.FAILED else None,
            failed_during=latest.failed_during if status == PaperStatus.FAILED else None,
            head_refine_warnings=latest.head_refine_warnings,
            classify_warnings=latest.classify_warnings,
            extract_warnings=latest.extract_warnings,
        )
        await pipeline_repo.save_status(paper_id, snapshot)

    async def update_classification(
        self,
        paper_id: str,
        classification: ParadigmClassification,
    ) -> None:
        async with get_async_session_factory()() as session:
            await self._begin_immediate(session)
            row = await session.get(PaperRow, paper_id)
            if row is None:
                msg = f"paper not found: {paper_id}"
                raise KeyError(msg)
            row.paradigm = classification.paradigm.value
            row.classification = classification.model_dump(mode="json")
            row.updated_at = datetime.now(UTC)
            await session.commit()

    async def update_paths(
        self,
        paper_id: str,
        *,
        graph_path: str | None = None,
        head_path: str | None = None,
        pdf_path: str | None = None,
    ) -> None:
        async with get_async_session_factory()() as session:
            await self._begin_immediate(session)
            row = await session.get(PaperRow, paper_id)
            if row is None:
                msg = f"paper not found: {paper_id}"
                raise KeyError(msg)
            if graph_path is not None:
                row.graph_path = graph_path
            if head_path is not None:
                row.head_path = head_path
            if pdf_path is not None:
                row.pdf_path = pdf_path
            row.updated_at = datetime.now(UTC)
            await session.commit()

    async def update_title(self, paper_id: str, title: str) -> None:
        async with get_async_session_factory()() as session:
            await self._begin_immediate(session)
            row = await session.get(PaperRow, paper_id)
            if row is None:
                msg = f"paper not found: {paper_id}"
                raise KeyError(msg)
            row.title = title
            row.updated_at = datetime.now(UTC)
            await session.commit()

    async def mark_preview_available(self, paper_id: str) -> None:
        async with get_async_session_factory()() as session:
            await self._begin_immediate(session)
            row = await session.get(PaperRow, paper_id)
            if row is None:
                msg = f"paper not found: {paper_id}"
                raise KeyError(msg)
            row.preview_available = True
            row.updated_at = datetime.now(UTC)
            await session.commit()

    async def get_pdf_path(self, paper_id: str) -> str | None:
        async with get_async_session_factory()() as session:
            row = await session.get(PaperRow, paper_id)
            if row is None:
                return None
            return row.pdf_path

    async def reset_for_reextract(self, paper_id: str) -> str:
        """Clear classification/paths/preview and atomically bump ``graph_version``."""
        async with get_async_session_factory()() as session:
            await self._begin_immediate(session)
            row = await session.get(PaperRow, paper_id, with_for_update=True)
            if row is None:
                msg = f"paper not found: {paper_id}"
                raise KeyError(msg)
            new_version = _bump_graph_version(row.graph_version)
            row.status = PaperStatus.PENDING.value
            row.paradigm = None
            row.classification = None
            row.graph_path = None
            row.head_path = None
            row.preview_available = False
            row.graph_version = new_version
            row.updated_at = datetime.now(UTC)
            await session.commit()
            return new_version

    async def get_graph_version(self, paper_id: str) -> str:
        """Return the persisted graph version, or the default for new papers."""
        async with get_async_session_factory()() as session:
            row = await session.get(PaperRow, paper_id)
            if row is None:
                msg = f"paper not found: {paper_id}"
                raise KeyError(msg)
            return row.graph_version or DEFAULT_GRAPH_VERSION

    async def update_graph_version(
        self,
        paper_id: str,
        *,
        graph_version: str,
        extractor_config_hash: str | None = None,
    ) -> None:
        async with get_async_session_factory()() as session:
            await self._begin_immediate(session)
            row = await session.get(PaperRow, paper_id)
            if row is None:
                msg = f"paper not found: {paper_id}"
                raise KeyError(msg)
            row.graph_version = graph_version
            if extractor_config_hash is not None:
                row.extractor_config_hash = extractor_config_hash
            row.updated_at = datetime.now(UTC)
            await session.commit()

    async def delete(self, paper_id: str) -> bool:
        async with get_async_session_factory()() as session:
            await self._begin_immediate(session)
            row = await session.get(PaperRow, paper_id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def bump_list_rank(self, paper_ids: tuple[str, ...] | list[str]) -> None:
        """Refresh ``created_at`` so demo fixtures stay visible in paginated list APIs."""
        now = datetime.now(UTC)
        async with get_async_session_factory()() as session:
            await self._begin_immediate(session)
            for paper_id in paper_ids:
                row = await session.get(PaperRow, paper_id)
                if row is not None:
                    row.created_at = now
                    row.updated_at = now
            await session.commit()

    async def _begin_immediate(self, session: AsyncSession) -> None:
        from sqlalchemy import text

        if session.bind is not None and session.bind.dialect.name == "sqlite":
            await session.execute(text("BEGIN IMMEDIATE"))


@lru_cache
def get_paper_repository() -> PaperRepository:
    return PaperRepository()
