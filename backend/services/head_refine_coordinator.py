# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Coordinate head refine persistence across disk and DB metadata."""

from __future__ import annotations

import asyncio
import logging
from functools import lru_cache

from backend.graph.head_store import HeadStore
from backend.repositories.paper_repository import PaperRepository, get_paper_repository
from backend.repositories.pipeline_repository import PipelineRepository, get_pipeline_repository
from backend.schemas.ingest_head import IngestHead, PersistedHeadRefine
from backend.schemas.paper import PaperStatus
from backend.services.paper_core_service import PaperCoreService
from backend.services.paper_warning_service import (
    PaperWarningService,
    WarningType,
    get_paper_warning_service,
)

logger = logging.getLogger(__name__)

# Dual-media write order (no distributed transaction in Python):
# 1. Pipeline warnings merge — idempotent, best-effort degrade codes.
# 2. Paper title (PENDING only) — DB metadata moves forward.
# 3. Canonical ``.head.json`` on disk — file arrives after logical data advance.
# 4. ``head_path`` pointer in papers row — DB catches up to the file.
#
# Retry contract: re-invoking ``apply`` with the same payload is safe. Disk step 3
# overwrites atomically; DB steps use upsert/merge semantics. If step 3 fails after
# 1–2, retry completes the file; if step 4 fails after 3, file is readable via
# deterministic ``HeadStore`` path and retry fixes the pointer.


class HeadRefineCoordinator:
    """Persist and hydrate refined ingest-head artefacts."""

    def __init__(
        self,
        *,
        core_service: PaperCoreService,
        warning_service: PaperWarningService,
        paper_repo: PaperRepository | None = None,
        pipeline_repo: PipelineRepository | None = None,
        head_store: HeadStore | None = None,
    ) -> None:
        self._core_service = core_service
        self._warning_service = warning_service
        self._paper_repo = paper_repo or get_paper_repository()
        self._pipeline_repo = pipeline_repo or get_pipeline_repository()
        self._head_store_override = head_store

    def _head_store(self) -> HeadStore:
        """Resolve disk store per call so ``GRAPH_DATA_DIR`` changes stay visible."""
        return self._head_store_override or HeadStore()

    async def apply(
        self,
        paper_id: str,
        *,
        merged: IngestHead,
        classifier_input: str,
        warnings: list[str] | None = None,
    ) -> None:
        """Persist head refine output with ordered, retry-safe dual-media writes."""
        if warnings:
            await self._warning_service.record(paper_id, WarningType.HEAD_REFINE, warnings)

        paper = await self._paper_repo.get(paper_id)
        if merged.title.strip() and paper is not None and paper.status == PaperStatus.PENDING:
            await self._core_service.update_title(paper_id, merged.title.strip())

        head_path = str(self._head_store()._path(paper_id))
        try:
            await asyncio.to_thread(
                self._head_store().save,
                paper_id,
                merged=merged,
                classifier_input=classifier_input,
                warnings=warnings,
            )
        except OSError:
            logger.error(
                "head_refine_disk_write_failed paper_id=%s path=%s",
                paper_id,
                head_path,
                exc_info=True,
            )
            raise

        await self._core_service.update_paths(paper_id, head_path=head_path)

    async def load_head(self, paper_id: str) -> IngestHead | None:
        record = await asyncio.to_thread(self._head_store().load, paper_id)
        return record.merged if record is not None else None

    async def load_record(self, paper_id: str) -> PersistedHeadRefine | None:
        return await asyncio.to_thread(self._head_store().load, paper_id)

    def load_head_sync(self, paper_id: str) -> IngestHead | None:
        record = self._head_store().load(paper_id)
        return record.merged if record is not None else None

    def load_record_sync(self, paper_id: str) -> PersistedHeadRefine | None:
        return self._head_store().load(paper_id)

    async def get_classifier_input(self, paper_id: str) -> str | None:
        record = await self.load_record(paper_id)
        if record is None:
            return None
        stripped = record.classifier_input.strip()
        return stripped or None

    def get_classifier_input_sync(self, paper_id: str) -> str | None:
        record = self.load_record_sync(paper_id)
        if record is None:
            return None
        stripped = record.classifier_input.strip()
        return stripped or None

    async def sync_warnings_from_disk(self, paper_id: str) -> None:
        record = await asyncio.to_thread(self._head_store().load, paper_id)
        if record is None or not record.warnings:
            return
        snapshot = await self._pipeline_repo.get_latest(paper_id)
        if snapshot is not None and snapshot.head_refine_warnings:
            return
        await self._warning_service.record(
            paper_id,
            WarningType.HEAD_REFINE,
            list(record.warnings),
        )


@lru_cache
def get_head_refine_coordinator() -> HeadRefineCoordinator:
    return HeadRefineCoordinator(
        core_service=PaperCoreService(),
        warning_service=get_paper_warning_service(),
    )
