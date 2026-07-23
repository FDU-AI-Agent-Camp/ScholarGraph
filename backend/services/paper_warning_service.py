# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Warning persistence facade for paper pipeline warning buckets.

Async-only public API: callers in LangGraph / EventBus / RAG handlers must
``await`` ``record`` / ``get``. No ``run_async`` bridge lives here — sync
callers are a design smell and must be made async upstream.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from backend.repositories.pipeline_repository import PipelineRepository, get_pipeline_repository
from backend.schemas.paper import PaperStatusData

__all__ = [
    "PaperWarningService",
    "WarningCategory",
    "WarningType",
    "get_paper_warning_service",
]


class WarningType(StrEnum):
    """Supported warning buckets stored on ``pipeline_runs``."""

    HEAD_REFINE = "head_refine"
    CLASSIFY = "classify"
    EXTRACT = "extract"


# Alias matching the step-A contract name (category / type are the same enum).
WarningCategory = WarningType


class PaperWarningService:
    """Read/write machine warning codes grouped by warning bucket."""

    def __init__(self, pipeline_repo: PipelineRepository | None = None) -> None:
        self._pipeline_repo = pipeline_repo or get_pipeline_repository()

    async def record(
        self,
        paper_id: str,
        category: WarningType,
        warnings: list[str],
    ) -> None:
        """Merge warnings into the selected bucket, ignoring empty payloads."""
        if not warnings:
            return
        kwargs = {
            WarningType.HEAD_REFINE: {"head_refine": warnings},
            WarningType.CLASSIFY: {"classify": warnings},
            WarningType.EXTRACT: {"extract": warnings},
        }[category]
        await self._pipeline_repo.record_warnings(paper_id, **kwargs)

    async def get(self, paper_id: str, category: WarningType) -> list[str]:
        """Return one warning bucket, or an empty list when no snapshot exists."""
        return self._bucket_from_snapshot(
            await self._pipeline_repo.get_latest(paper_id),
            category,
        )

    async def get_extract_and_classify(self, paper_id: str) -> tuple[list[str], list[str]]:
        """Fetch extract + classify buckets from one snapshot read."""
        snapshot = await self._pipeline_repo.get_latest(paper_id)
        if snapshot is None:
            return [], []
        return list(snapshot.extract_warnings), list(snapshot.classify_warnings)

    @staticmethod
    def _bucket_from_snapshot(
        snapshot: PaperStatusData | None,
        category: WarningType,
    ) -> list[str]:
        if snapshot is None:
            return []
        if category == WarningType.HEAD_REFINE:
            return list(snapshot.head_refine_warnings)
        if category == WarningType.CLASSIFY:
            return list(snapshot.classify_warnings)
        return list(snapshot.extract_warnings)


@lru_cache
def get_paper_warning_service() -> PaperWarningService:
    return PaperWarningService()
