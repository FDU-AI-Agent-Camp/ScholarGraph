# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Preview graph lifecycle facade spanning paper metadata and pipeline state."""

from __future__ import annotations

from backend.repositories import run_async
from backend.repositories.paper_repository import PaperRepository, get_paper_repository
from backend.repositories.pipeline_repository import PipelineRepository, get_pipeline_repository
from backend.schemas.graph import UnifiedPaperGraph
from backend.services.paper_core_service import PaperCoreService


class PreviewGraphFacade:
    """Coordinate preview graph persistence and preview availability state."""

    def __init__(
        self,
        *,
        core_service: PaperCoreService,
        paper_repo: PaperRepository | None = None,
        pipeline_repo: PipelineRepository | None = None,
    ) -> None:
        self._core_service = core_service
        self._paper_repo = paper_repo or get_paper_repository()
        self._pipeline_repo = pipeline_repo or get_pipeline_repository()

    def save(self, paper_id: str, graph: UnifiedPaperGraph) -> None:
        run_async(self._pipeline_repo.save_preview_graph(paper_id, graph))

    def get(self, paper_id: str) -> UnifiedPaperGraph | None:
        return run_async(self._pipeline_repo.get_preview_graph(paper_id))

    def clear(self, paper_id: str) -> None:
        run_async(self._pipeline_repo.clear_preview_graph(paper_id))

    def mark_available(self, paper_id: str) -> None:
        self._core_service.mark_preview_available(paper_id)

    def is_available(self, paper_id: str) -> bool:
        paper = run_async(self._paper_repo.get(paper_id))
        if paper is not None and paper.preview_available:
            return True
        return self.get(paper_id) is not None

    async def ais_available(self, paper_id: str) -> bool:
        """Async availability check for detail assemblers."""
        paper = await self._paper_repo.get(paper_id)
        if paper is not None and paper.preview_available:
            return True
        return await self._pipeline_repo.get_preview_graph(paper_id) is not None
