# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Replace-paper-index + generation-guard helpers for ``VectorStore`` (P13).

Keeps ``vector_store.py`` under the D-12 line budget while owning:

- run-id snapshot upsert → activate → async cleanup of the previous run;
- ``IndexingRunRegistry`` begin/revoke/may_activate gating;
- sticky revoke on cancel/refuse (timeout-path compensate must still see run_id);
- structured ``[Generation Guard]`` refuse-activate logs.
"""

from __future__ import annotations

import asyncio
import logging
import warnings
from typing import TYPE_CHECKING

from backend.rag.vector_store_utils import _generate_run_id, _validate_evidence_paper_ids

if TYPE_CHECKING:
    from backend.rag.models import PaperChunk, PaperEntity, PaperRelation
    from backend.services.paper_service import PaperService

logger = logging.getLogger(__name__)

# Structured marker for ELK / race-amplification tests (P13 orphan-thread gate).
GENERATION_GUARD_LOG_PREFIX = "[Generation Guard]"


class ObsoleteGenerationWarning(UserWarning):
    """Raised when a superseded index run_id attempts to activate after a newer generation.

    Emitted via ``warnings.warn`` on the refuse-activate path so concurrency tests
    can assert generation-guard behavior with ``pytest.warns``.
    """


class ReplacePaperIndexMixin:
    """Mixin: run-id snapshot replace with revoke / generation-guard activation."""

    _paper_service: PaperService | None
    _pending_cleanups: dict[str, set[asyncio.Task[None]]]
    _replace_locks: dict[str, asyncio.Lock]

    async def delete_by_paper(self, paper_id: str) -> None:
        raise NotImplementedError

    async def index_chunks(self, chunks: list[PaperChunk]) -> None:
        raise NotImplementedError

    async def index_entities(self, entities: list[PaperEntity]) -> None:
        raise NotImplementedError

    async def index_relations(self, relations: list[PaperRelation]) -> None:
        raise NotImplementedError

    async def _await_pending_cleanups(self, paper_id: str) -> None:
        raise NotImplementedError

    async def _index_chunks(self, chunks: list[PaperChunk], *, run_id: str | None) -> None:
        raise NotImplementedError

    async def _index_entities(self, entities: list[PaperEntity], *, run_id: str | None) -> None:
        raise NotImplementedError

    async def _index_relations(self, relations: list[PaperRelation], *, run_id: str | None) -> None:
        raise NotImplementedError

    async def _cleanup_run_safely(self, paper_id: str, run_id: str) -> None:
        raise NotImplementedError

    async def _cleanup_run(self, paper_id: str, run_id: str) -> None:
        raise NotImplementedError

    def clear_chunk_text_lru(self) -> None:
        raise NotImplementedError

    async def replace_paper_index(
        self,
        paper_id: str,
        *,
        chunks: list[PaperChunk],
        entities: list[PaperEntity],
        relations: list[PaperRelation],
    ) -> None:
        """Replace all indexed evidence for one paper using index_run_id snapshot switching.

        A new run id is created, data is upserted with that run id, and only after
        all three collections succeed is the new run activated. If anything fails,
        queries continue to see the previously active run. Old runs are cleaned up
        asynchronously after activation.
        """
        _validate_evidence_paper_ids(paper_id, chunks, entities, relations)

        if self._paper_service is None:
            await self.delete_by_paper(paper_id)
            await self.index_chunks(chunks)
            await self.index_entities(entities)
            await self.index_relations(relations)
            return

        previous_run_id: str | None = None
        activated = False
        async with self._replace_locks.setdefault(paper_id, asyncio.Lock()):
            previous_run_id = await self._paper_service.get_active_run_id(paper_id)
            await self._await_pending_cleanups(paper_id)

            from backend.rag.indexing_run_registry import get_indexing_run_registry

            registry = get_indexing_run_registry()
            run_id = _generate_run_id()
            registry.begin(paper_id, run_id)
            try:
                await self._index_chunks(chunks, run_id=run_id)
                await self._index_entities(entities, run_id=run_id)
                await self._index_relations(relations, run_id=run_id)

                # Cancellation / wait_for timeout may still reach sync code after the
                # last await; refuse activation when revoked or the Task is cancelling.
                current_task = asyncio.current_task()
                is_cancelling = bool(current_task is not None and getattr(current_task, "cancelling", lambda: 0)() > 0)
                if is_cancelling or not registry.may_activate(paper_id, run_id):
                    registry.revoke(paper_id, run_id)
                    await self._log_generation_guard_abort(paper_id, run_id)
                    await self._cleanup_run_safely(paper_id, run_id)
                    # Keep revoke sticky so timeout-path compensate can still find run_id.
                    if is_cancelling:
                        raise asyncio.CancelledError()
                    return

                await self._paper_service.set_active_run_id(paper_id, run_id)
                activated = True
                registry.clear(paper_id, run_id)
                self.clear_chunk_text_lru()
            except asyncio.CancelledError:
                registry.revoke(paper_id, run_id)
                await self._log_generation_guard_abort(paper_id, run_id)
                await self._cleanup_run_safely(paper_id, run_id)
                # Do not clear revoke: zombie to_thread may still upsert after cancel.
                raise
            except Exception:
                registry.revoke(paper_id, run_id)
                await self._cleanup_run_safely(paper_id, run_id)
                registry.clear(paper_id, run_id)
                raise

        if activated and previous_run_id:
            task = asyncio.create_task(self._cleanup_run(paper_id, previous_run_id))
            self._pending_cleanups.setdefault(paper_id, set()).add(task)
            task.add_done_callback(lambda _: self._pending_cleanups.get(paper_id, set()).discard(task))

    async def _log_generation_guard_abort(self, paper_id: str, run_id: str) -> None:
        """Emit a stable ops marker when a superseded run must not activate."""
        active: str | None = None
        if self._paper_service is not None:
            try:
                active = await self._paper_service.get_active_run_id(paper_id)
            except Exception:
                active = None
        current = active if active else "<none>"
        message = (
            f"{GENERATION_GUARD_LOG_PREFIX} {run_id} is obsolete "
            f"(current active is {current}). Aborting database update."
        )
        logger.warning(
            message,
            extra={
                "paper_id": paper_id,
                "run_id": run_id,
                "active_run_id": active,
                "generation_guard": True,
            },
        )
        warnings.warn(message, ObsoleteGenerationWarning, stacklevel=2)
