# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Warning persistence facade for paper pipeline warning buckets."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from backend.repositories import run_async
from backend.repositories.pipeline_repository import PipelineRepository, get_pipeline_repository
from backend.schemas.paper import PaperStatusData


class WarningType(StrEnum):
    """Supported warning buckets stored on ``pipeline_runs``."""

    HEAD_REFINE = "head_refine"
    CLASSIFY = "classify"
    EXTRACT = "extract"


class PaperWarningService:
    """Read/write machine warning codes grouped by warning bucket."""

    def __init__(self, pipeline_repo: PipelineRepository | None = None) -> None:
        self._pipeline_repo = pipeline_repo or get_pipeline_repository()

    def record(self, paper_id: str, warning_type: WarningType, warnings: list[str]) -> None:
        """Merge warnings into the selected bucket, ignoring empty payloads."""
        run_async(self.arecord(paper_id, warning_type, warnings))

    async def arecord(self, paper_id: str, warning_type: WarningType, warnings: list[str]) -> None:
        """Async merge of warnings into the selected bucket."""
        if not warnings:
            return
        kwargs = {
            WarningType.HEAD_REFINE: {"head_refine": warnings},
            WarningType.CLASSIFY: {"classify": warnings},
            WarningType.EXTRACT: {"extract": warnings},
        }[warning_type]
        await self._pipeline_repo.record_warnings(paper_id, **kwargs)

    def get(self, paper_id: str, warning_type: WarningType) -> list[str]:
        """Return one warning bucket, or an empty list when no snapshot exists."""
        return self._bucket_from_snapshot(
            run_async(self._pipeline_repo.get_latest(paper_id)),
            warning_type,
        )

    async def aget(self, paper_id: str, warning_type: WarningType) -> list[str]:
        """Async variant of ``get`` for detail assemblers."""
        return self._bucket_from_snapshot(
            await self._pipeline_repo.get_latest(paper_id),
            warning_type,
        )

    async def aget_extract_and_classify(self, paper_id: str) -> tuple[list[str], list[str]]:
        """Fetch extract + classify buckets from one snapshot read."""
        snapshot = await self._pipeline_repo.get_latest(paper_id)
        if snapshot is None:
            return [], []
        return list(snapshot.extract_warnings), list(snapshot.classify_warnings)

    @staticmethod
    def _bucket_from_snapshot(
        snapshot: PaperStatusData | None,
        warning_type: WarningType,
    ) -> list[str]:
        if snapshot is None:
            return []
        if warning_type == WarningType.HEAD_REFINE:
            return list(snapshot.head_refine_warnings)
        if warning_type == WarningType.CLASSIFY:
            return list(snapshot.classify_warnings)
        return list(snapshot.extract_warnings)


@lru_cache
def get_paper_warning_service() -> PaperWarningService:
    return PaperWarningService()
