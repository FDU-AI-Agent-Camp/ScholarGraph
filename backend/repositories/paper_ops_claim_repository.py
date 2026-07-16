"""Durable cluster-wide wipe mutex for force delete ∪ force reextract.

Replaces the process-local ``_reextract_inflight`` set. Cross-worker safety is
provided by a ``paper_ops_claims`` row (stealable after TTL). On PostgreSQL the
short acquire transaction also takes ``pg_advisory_xact_lock`` so concurrent
workers serialize at the engine layer; SQLite relies on optimistic INSERT /
conditional UPDATE (no multi-connection ``BEGIN IMMEDIATE`` storm).

Within a single process, an ``asyncio.Lock`` serialises acquire/release bursts so
aiosqlite cannot live-lock under ``force_reextract`` contention tests.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from sqlalchemy import delete, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.db.base import get_async_session_factory
from backend.db.models import PaperOpsClaimRow
from backend.repositories.pipeline_sync import get_pipeline_sync_session_factory

logger = logging.getLogger(__name__)

# Lazy per-running-loop gate: a module-level ``asyncio.Lock()`` binds to the first
# loop that touches it and breaks under pytest's fresh loops ("bound to a different
# event loop"). Recreate when the running loop identity changes.
_PROCESS_ACQUIRE_GATE: asyncio.Lock | None = None
_PROCESS_ACQUIRE_GATE_LOOP: asyncio.AbstractEventLoop | None = None


def _get_process_acquire_gate() -> asyncio.Lock:
    global _PROCESS_ACQUIRE_GATE, _PROCESS_ACQUIRE_GATE_LOOP
    loop = asyncio.get_running_loop()
    if _PROCESS_ACQUIRE_GATE is None or _PROCESS_ACQUIRE_GATE_LOOP is not loop:
        _PROCESS_ACQUIRE_GATE = asyncio.Lock()
        _PROCESS_ACQUIRE_GATE_LOOP = loop
    return _PROCESS_ACQUIRE_GATE


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _advisory_lock_key(paper_id: str) -> int:
    """Map paper_id to a signed 64-bit key for ``pg_advisory_xact_lock``."""
    digest = hashlib.sha256(f"paper_ops:{paper_id}".encode()).digest()[:8]
    return int.from_bytes(digest, "big", signed=True)


class PaperOpsClaimConflictError(Exception):
    """Raised when another owner already holds a non-expired claim."""

    def __init__(self, paper_id: str, *, current_operation: str | None = None) -> None:
        self.paper_id = paper_id
        self.current_operation = current_operation
        super().__init__(f"paper ops claim held for {paper_id}")


class PaperOpsClaimRepository:
    """Acquire / release durable ``paper_ops_claims`` rows."""

    async def try_acquire(self, paper_id: str, *, operation: str) -> str:
        """Insert or steal an expired claim. Returns owner_token or raises conflict."""
        async with _get_process_acquire_gate():
            return await self._try_acquire_unlocked(paper_id, operation=operation)

    async def _try_acquire_unlocked(self, paper_id: str, *, operation: str) -> str:
        settings = get_settings()
        ttl = float(settings.paper_ops_claim_ttl_seconds)
        now = _utc_now()
        expires_at = now + timedelta(seconds=ttl)
        owner_token = uuid.uuid4().hex

        async with get_async_session_factory()() as session:
            await self._pg_advisory_xact_lock(session, paper_id)
            existing = await session.get(PaperOpsClaimRow, paper_id)
            if existing is None:
                session.add(
                    PaperOpsClaimRow(
                        paper_id=paper_id,
                        operation=operation,
                        owner_token=owner_token,
                        acquired_at=now,
                        expires_at=expires_at,
                    )
                )
                try:
                    await session.commit()
                except IntegrityError as exc:
                    await session.rollback()
                    raise PaperOpsClaimConflictError(paper_id) from exc
                return owner_token

            if _as_utc(existing.expires_at) > now:
                op = existing.operation
                await session.rollback()
                raise PaperOpsClaimConflictError(paper_id, current_operation=op)

            existing.operation = operation
            existing.owner_token = owner_token
            existing.acquired_at = now
            existing.expires_at = expires_at
            await session.commit()
            logger.info(
                "paper_ops_claim_stolen_expired",
                extra={"paper_id": paper_id, "operation": operation},
            )
            return owner_token

    async def release(self, paper_id: str, owner_token: str) -> bool:
        """Delete claim only when *owner_token* matches. Returns whether a row was removed."""
        async with _get_process_acquire_gate():
            async with get_async_session_factory()() as session:
                result = await session.execute(
                    delete(PaperOpsClaimRow).where(
                        PaperOpsClaimRow.paper_id == paper_id,
                        PaperOpsClaimRow.owner_token == owner_token,
                    )
                )
                await session.commit()
                return int(getattr(result, "rowcount", 0) or 0) > 0

    async def force_release(self, paper_id: str) -> bool:
        """Evict any claim for *paper_id* (Cascading Kill / crash recovery)."""
        async with _get_process_acquire_gate():
            async with get_async_session_factory()() as session:
                result = await session.execute(delete(PaperOpsClaimRow).where(PaperOpsClaimRow.paper_id == paper_id))
                await session.commit()
                return int(getattr(result, "rowcount", 0) or 0) > 0

    def force_release_sync(self, paper_id: str) -> bool:
        """Sync force-evict for watchdog dedicated OS thread."""
        factory = get_pipeline_sync_session_factory()
        with factory() as db:
            row = db.get(PaperOpsClaimRow, paper_id)
            if row is None:
                return False
            db.delete(row)
            db.commit()
            return True

    async def is_held(self, paper_id: str, *, now: datetime | None = None) -> bool:
        clock = now or _utc_now()
        async with get_async_session_factory()() as session:
            row = await session.get(PaperOpsClaimRow, paper_id)
            if row is None:
                return False
            return _as_utc(row.expires_at) > clock

    def is_held_sync(self, paper_id: str, *, now: datetime | None = None) -> bool:
        clock = now or _utc_now()
        factory = get_pipeline_sync_session_factory()
        with factory() as db:
            row = db.get(PaperOpsClaimRow, paper_id)
            if row is None:
                return False
            return _as_utc(row.expires_at) > clock

    async def clear_all(self) -> None:
        """Test helper: drop every claim row (no-op if table missing)."""
        async with _get_process_acquire_gate():
            async with get_async_session_factory()() as session:
                try:
                    await session.execute(delete(PaperOpsClaimRow))
                    await session.commit()
                except Exception:
                    await session.rollback()

    def clear_all_sync(self) -> None:
        """Test helper: sync clear for fixtures that cannot await."""
        factory = get_pipeline_sync_session_factory()
        with factory() as db:
            bind = db.get_bind()
            inspector = inspect(bind)
            if not inspector.has_table(PaperOpsClaimRow.__tablename__):
                return
            db.execute(delete(PaperOpsClaimRow))
            db.commit()

    async def seed_claim_for_tests(
        self,
        paper_id: str,
        *,
        operation: str,
        owner_token: str | None = None,
        ttl_seconds: float = 600.0,
    ) -> str:
        """Insert a claim without race checks (test / chaos planting)."""
        token = owner_token or uuid.uuid4().hex
        now = _utc_now()
        async with _get_process_acquire_gate():
            async with get_async_session_factory()() as session:
                session.add(
                    PaperOpsClaimRow(
                        paper_id=paper_id,
                        operation=operation,
                        owner_token=token,
                        acquired_at=now,
                        expires_at=now + timedelta(seconds=ttl_seconds),
                    )
                )
                await session.commit()
        return token

    async def _pg_advisory_xact_lock(self, session: AsyncSession, paper_id: str) -> None:
        if session.bind is None or session.bind.dialect.name != "postgresql":
            return
        key = _advisory_lock_key(paper_id)
        await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


@lru_cache
def get_paper_ops_claim_repository() -> PaperOpsClaimRepository:
    return PaperOpsClaimRepository()


def reset_paper_ops_claim_repository() -> None:
    """Drop cached repository singleton (tests that swap DATABASE_URL)."""
    global _PROCESS_ACQUIRE_GATE, _PROCESS_ACQUIRE_GATE_LOOP
    _PROCESS_ACQUIRE_GATE = None
    _PROCESS_ACQUIRE_GATE_LOOP = None
    get_paper_ops_claim_repository.cache_clear()
