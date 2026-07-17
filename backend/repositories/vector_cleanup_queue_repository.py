# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Durable Wave-2 vector cleanup outbox (``vector_cleanup_queue``).

Persists delayed ``delete_run`` tombstones so a process restart cannot evaporate
the in-memory ``asyncio.create_task`` scheduled after force DELETE / reextract.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from backend.db.base import get_async_session_factory
from backend.db.models import VectorCleanupQueueRow
from backend.repositories.pipeline_sync import get_pipeline_sync_session_factory

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class VectorCleanupJob:
    id: int
    paper_id: str
    run_id: str
    create_at: datetime
    execute_at: datetime


class VectorCleanupQueueRepository:
    """Enqueue / list / ack Wave-2 Chroma scrub jobs."""

    def enqueue_sync(
        self,
        paper_id: str,
        run_id: str,
        *,
        execute_at: datetime,
        create_at: datetime | None = None,
    ) -> bool:
        """Insert tombstone. Returns False when ``(paper_id, run_id)`` already exists."""
        created = create_at or _utc_now()
        factory = get_pipeline_sync_session_factory()
        with factory() as db:
            db.add(
                VectorCleanupQueueRow(
                    paper_id=paper_id,
                    run_id=run_id,
                    create_at=created,
                    execute_at=execute_at,
                )
            )
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                return False
            return True

    def list_pending_sync(self) -> list[VectorCleanupJob]:
        factory = get_pipeline_sync_session_factory()
        with factory() as db:
            rows = db.scalars(select(VectorCleanupQueueRow).order_by(VectorCleanupQueueRow.execute_at)).all()
            return [_to_job(row) for row in rows]

    def list_due_sync(self, *, now: datetime | None = None) -> list[VectorCleanupJob]:
        clock = now or _utc_now()
        factory = get_pipeline_sync_session_factory()
        with factory() as db:
            rows = db.scalars(
                select(VectorCleanupQueueRow)
                .where(VectorCleanupQueueRow.execute_at <= clock)
                .order_by(VectorCleanupQueueRow.execute_at)
            ).all()
            return [_to_job(row) for row in rows]

    def delete_by_paper_run_sync(self, paper_id: str, run_id: str) -> bool:
        factory = get_pipeline_sync_session_factory()
        with factory() as db:
            result = db.execute(
                delete(VectorCleanupQueueRow).where(
                    VectorCleanupQueueRow.paper_id == paper_id,
                    VectorCleanupQueueRow.run_id == run_id,
                )
            )
            db.commit()
            return int(getattr(result, "rowcount", 0) or 0) > 0

    def clear_all_sync(self) -> None:
        factory = get_pipeline_sync_session_factory()
        with factory() as db:
            bind = db.get_bind()
            from sqlalchemy import inspect

            inspector = inspect(bind)
            if not inspector.has_table(VectorCleanupQueueRow.__tablename__):
                return
            db.execute(delete(VectorCleanupQueueRow))
            db.commit()

    async def list_pending(self) -> list[VectorCleanupJob]:
        async with get_async_session_factory()() as session:
            result = await session.scalars(select(VectorCleanupQueueRow).order_by(VectorCleanupQueueRow.execute_at))
            return [_to_job(row) for row in result.all()]

    async def delete_by_paper_run(self, paper_id: str, run_id: str) -> bool:
        async with get_async_session_factory()() as session:
            result = await session.execute(
                delete(VectorCleanupQueueRow).where(
                    VectorCleanupQueueRow.paper_id == paper_id,
                    VectorCleanupQueueRow.run_id == run_id,
                )
            )
            await session.commit()
            return int(getattr(result, "rowcount", 0) or 0) > 0


def _to_job(row: VectorCleanupQueueRow) -> VectorCleanupJob:
    return VectorCleanupJob(
        id=int(row.id),
        paper_id=row.paper_id,
        run_id=row.run_id,
        create_at=_as_utc(row.create_at),
        execute_at=_as_utc(row.execute_at),
    )


@lru_cache
def get_vector_cleanup_queue_repository() -> VectorCleanupQueueRepository:
    return VectorCleanupQueueRepository()


def reset_vector_cleanup_queue_repository() -> None:
    get_vector_cleanup_queue_repository.cache_clear()
