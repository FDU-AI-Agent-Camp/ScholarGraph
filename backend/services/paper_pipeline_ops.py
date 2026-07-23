# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Paper pipeline operations service (P13 LoD harden).

External RAG / watchdog / re-extract callers must use ``PaperService`` public
facade methods (e.g. ``promote_paper_to_terminal_status``) or inject
``PaperPipelineOpsService`` in tests instead of touching ``_pipeline_repo``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from functools import lru_cache

from backend.events.bus import get_event_bus
from backend.events.types import RagIndexed
from backend.repositories.pipeline_repository import PipelineRepository, get_pipeline_repository
from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage

logger = logging.getLogger(__name__)

RAG_INDEXING_STUCK_WARNING = "rag_indexing_stuck_timeout"
DEFAULT_STUCK_INDEXING_MESSAGE = "建图完成，但向量索引超时未完成（indexing watchdog）；可稍后重试索引或重新抽取"
DEFAULT_RAG_INDEX_FAILED_MESSAGE = "建图完成，但向量索引构建失败"
P13_WATCHDOG_HEAL_TAG = "[P13_WATCHDOG_HEAL]"

__all__ = [
    "DEFAULT_RAG_INDEX_FAILED_MESSAGE",
    "DEFAULT_STUCK_INDEXING_MESSAGE",
    "P13_WATCHDOG_HEAL_TAG",
    "PaperPipelineOpsService",
    "RAG_INDEXING_STUCK_WARNING",
    "get_paper_pipeline_ops_service",
]


class PaperPipelineOpsService:
    """Pipeline snapshot, generation guard, and terminal promote operations."""

    def __init__(self, pipeline_repo: PipelineRepository | None = None) -> None:
        self._pipeline_repo = pipeline_repo or get_pipeline_repository()

    async def get_pipeline_snapshot(self, paper_id: str) -> PaperStatusData | None:
        """Return the latest pipeline status snapshot, or None if absent."""
        return await self._pipeline_repo.get_latest(paper_id)

    async def save_pipeline_snapshot(self, paper_id: str, snapshot: PaperStatusData) -> None:
        """Persist a validated pipeline status snapshot (papers + pipeline_runs)."""
        await self._pipeline_repo.save_status(paper_id, snapshot)

    async def repair_indexing_contract_if_indexing(
        self,
        paper_id: str,
        *,
        message: str | None = None,
    ) -> PaperStatusData | None:
        """Conditionally repair INDEXING drift without demoting a concurrent terminal promote."""
        return await self._pipeline_repo.repair_indexing_contract_if_indexing(
            paper_id,
            message=message,
        )

    async def touch_indexing_heartbeat(self, paper_id: str, *, at: datetime | None = None) -> bool:
        """Pulse ``indexing_heartbeat`` while the paper remains INDEXING."""
        return await self._pipeline_repo.touch_indexing_heartbeat(paper_id, at=at)

    async def list_stuck_indexing_papers(
        self,
        *,
        older_than: datetime | None = None,
        heartbeat_stale_before: datetime | None = None,
        limit: int = 200,
    ) -> list[tuple[str, datetime | None, datetime | None]]:
        """List stuck INDEXING papers for the async macro watchdog path."""
        return await self._pipeline_repo.list_stuck_indexing_papers(
            older_than=older_than,
            heartbeat_stale_before=heartbeat_stale_before,
            limit=limit,
        )

    async def reset_pipeline_for_reextract(self, paper_id: str, *, message: str) -> PaperStatusData:
        """Reset pipeline_runs ephemeral state before re-queueing extract."""
        return await self._pipeline_repo.reset_for_reextract(paper_id, message=message)

    async def get_pipeline_generation_id(self, paper_id: str) -> str | None:
        """Return the active extract-generation token, or ``None`` if unset."""
        return await self._pipeline_repo.get_pipeline_generation_id(paper_id)

    async def begin_pipeline_generation(self, paper_id: str) -> str:
        """Mint and persist a new extract-generation token (terminal write guard)."""
        return await self._pipeline_repo.begin_pipeline_generation(paper_id)

    async def invalidate_pipeline_generation(self, paper_id: str) -> None:
        """Clear the extract-generation token (orphan late-write defense)."""
        await self._pipeline_repo.set_pipeline_generation_id(paper_id, None)

    async def promote_paper_to_terminal_status(
        self,
        paper_id: str,
        *,
        success: bool,
        preferred_terminal: PaperStatus | None = None,
        warning_message: str | None = None,
        warning_codes: list[str] | None = None,
        message_override: str | None = None,
        publish_rag_indexed: bool = True,
    ) -> PaperStatusData:
        """Promote INDEXING → ready / ready_with_warnings after RAG index attempt.

        Optionally publishes ``RagIndexed`` so callers need not touch EventBus + repo.
        """
        from backend.graph.state import STAGE_PERCENT
        from backend.services.pipeline_status_service import (
            DEFAULT_STAGE_MESSAGES,
            validate_failed_error_fields,
            validate_status_contract,
        )

        preferred = preferred_terminal or PaperStatus.READY
        if preferred not in {PaperStatus.READY, PaperStatus.READY_WITH_WARNINGS}:
            preferred = PaperStatus.READY

        append_warnings: list[str] | None
        if not success:
            append_warnings = list(warning_codes or ["rag_index_failed"])
            status = PaperStatus.READY_WITH_WARNINGS
            message = message_override or DEFAULT_RAG_INDEX_FAILED_MESSAGE
        elif preferred == PaperStatus.READY_WITH_WARNINGS:
            append_warnings = None
            status = PaperStatus.READY_WITH_WARNINGS
            message = warning_message or "建图完成，但图谱置信度未达门控，请复核"
        else:
            append_warnings = None
            status = PaperStatus.READY
            message = DEFAULT_STAGE_MESSAGES[PipelineStage.READY]

        stage = PipelineStage.READY
        percent = STAGE_PERCENT[PipelineStage.READY]
        validate_status_contract(status=status, stage=stage, percent=percent)
        validate_failed_error_fields(status=status, error_code=None, failed_during=None)

        now = datetime.now(UTC)
        existing = await self.get_pipeline_snapshot(paper_id)
        if existing is None:
            msg = f"pipeline run missing for paper {paper_id}"
            raise RuntimeError(msg)
        if existing.status != PaperStatus.INDEXING:
            from backend.services.errors import InvalidStateTransitionError

            raise InvalidStateTransitionError(
                f"refuse promote_paper_to_terminal_status: expected INDEXING, got {existing.status.value}",
                from_status=existing.status.value,
                to_status=status.value,
                paper_id=paper_id,
            )
        merged_extract_warnings = list(existing.extract_warnings)
        if append_warnings:
            merged_extract_warnings = list(dict.fromkeys([*merged_extract_warnings, *append_warnings]))
        snapshot = PaperStatusData(
            paper_id=paper_id,
            status=status,
            percent=percent,
            stage=stage,
            message=message,
            updated_at=now,
            preview_available=bool(existing.preview_available),
            error_code=None,
            failed_during=None,
            head_refine_warnings=list(existing.head_refine_warnings),
            classify_warnings=list(existing.classify_warnings),
            extract_warnings=merged_extract_warnings,
        )
        await self.save_pipeline_snapshot(paper_id, snapshot)
        if publish_rag_indexed:
            await get_event_bus().publish(
                RagIndexed(
                    paper_id=paper_id,
                    success=success,
                    terminal_status=snapshot.status,
                ),
            )
        return snapshot

    async def promote_stuck_indexing_paper(
        self,
        paper_id: str,
        *,
        warning_code: str = RAG_INDEXING_STUCK_WARNING,
        message: str | None = None,
        publish_rag_indexed: bool = True,
    ) -> bool:
        """Force-promote one stuck INDEXING paper (async path). Returns whether changed."""
        from backend.graph.state import STAGE_PERCENT
        from backend.services.pipeline_status_service import (
            validate_failed_error_fields,
            validate_status_contract,
        )

        existing = await self.get_pipeline_snapshot(paper_id)
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
            message=message or DEFAULT_STUCK_INDEXING_MESSAGE,
            updated_at=now,
            preview_available=bool(existing.preview_available),
            error_code=None,
            failed_during=None,
            head_refine_warnings=list(existing.head_refine_warnings),
            classify_warnings=list(existing.classify_warnings),
            extract_warnings=merged,
        )
        await self.save_pipeline_snapshot(paper_id, snapshot)
        if publish_rag_indexed:
            # Prefer async publish on the caller's loop to avoid bridge-loop ghost sync.
            await get_event_bus().publish(
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

    def promote_stuck_indexing_paper_sync(
        self,
        paper_id: str,
        *,
        warning_code: str = RAG_INDEXING_STUCK_WARNING,
        message: str | None = None,
        publish_rag_indexed: bool = True,
    ) -> bool:
        """Sync promote for the dedicated watchdog thread (main-loop starvation safe)."""
        from backend.repositories.pipeline_sync import promote_stuck_indexing_row_sync

        changed = promote_stuck_indexing_row_sync(
            paper_id,
            warning_code=warning_code,
            message=message or DEFAULT_STUCK_INDEXING_MESSAGE,
        )
        if not changed:
            return False
        if publish_rag_indexed:
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

    def list_stuck_indexing_paper_ids_sync(
        self,
        *,
        older_than: datetime | None = None,
        heartbeat_stale_before: datetime | None = None,
        limit: int = 200,
    ) -> list[str]:
        """Sync stuck-paper listing for the out-of-loop watchdog thread."""
        from backend.repositories.pipeline_sync import list_stuck_indexing_paper_ids_sync

        return list_stuck_indexing_paper_ids_sync(
            older_than=older_than,
            heartbeat_stale_before=heartbeat_stale_before,
            limit=limit,
        )

    async def list_orphan_pipeline_paper_ids(
        self,
        *,
        older_than: datetime | None = None,
        limit: int = 200,
    ) -> list[str]:
        """List pending/processing papers for cold-boot orphan reconcile."""
        from backend.repositories.pipeline_sync import list_orphan_pipeline_paper_ids_sync

        return list_orphan_pipeline_paper_ids_sync(older_than=older_than, limit=limit)

    def list_stuck_processing_paper_ids_sync(
        self,
        *,
        older_than: datetime,
        limit: int = 200,
    ) -> list[str]:
        """Sync listing of wall-clock stuck PROCESSING papers."""
        from backend.repositories.pipeline_sync import list_stuck_processing_paper_ids_sync

        return list_stuck_processing_paper_ids_sync(older_than=older_than, limit=limit)

    def list_stuck_pending_paper_ids_sync(
        self,
        *,
        older_than: datetime,
        limit: int = 200,
    ) -> list[str]:
        """Sync listing of wall-clock stuck PENDING papers (queue backlog)."""
        from backend.repositories.pipeline_sync import list_stuck_pending_paper_ids_sync

        return list_stuck_pending_paper_ids_sync(older_than=older_than, limit=limit)

    def fail_orphaned_pipeline_paper_sync(
        self,
        paper_id: str,
        *,
        error_code: str,
        message: str,
    ) -> bool:
        """Sync fail pending/processing → failed (daemon / cold-boot safe)."""
        from backend.repositories.pipeline_sync import fail_orphaned_pipeline_row_sync

        return fail_orphaned_pipeline_row_sync(
            paper_id,
            error_code=error_code,
            message=message,
        )

    def touch_processing_lease_sync(self, paper_id: str) -> bool:
        """Renew PROCESSING ``updated_at`` while in-memory work remains alive."""
        from backend.repositories.pipeline_sync import touch_processing_lease_sync

        return touch_processing_lease_sync(paper_id)

    async def fail_orphaned_pipeline_paper(
        self,
        paper_id: str,
        *,
        error_code: str,
        message: str,
    ) -> bool:
        """Async wrapper around sync fail for cold-boot reconcile."""
        return self.fail_orphaned_pipeline_paper_sync(
            paper_id,
            error_code=error_code,
            message=message,
        )

    async def clear_ephemeral_pipeline_state(self, paper_id: str) -> None:
        """Clear preview graph and other ephemeral pipeline_runs fields."""
        await self._pipeline_repo.clear_ephemeral_pipeline_state(paper_id)


@lru_cache
def get_paper_pipeline_ops_service() -> PaperPipelineOpsService:
    return PaperPipelineOpsService()
