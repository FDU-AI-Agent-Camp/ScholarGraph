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
        async with get_async_session_factory()() as session:
            await self._begin_immediate(session)
            row = await session.get(PaperRow, paper_id)
            if row is None:
                msg = f"paper not found: {paper_id}"
                raise KeyError(msg)
            row.status = status.value
            row.updated_at = datetime.now(UTC)
            await session.commit()

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

    async def _begin_immediate(self, session: AsyncSession) -> None:
        from sqlalchemy import text

        if session.bind is not None and session.bind.dialect.name == "sqlite":
            await session.execute(text("BEGIN IMMEDIATE"))


@lru_cache
def get_paper_repository() -> PaperRepository:
    return PaperRepository()
