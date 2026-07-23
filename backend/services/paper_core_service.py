# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Core paper metadata operations backed by ``PaperRepository``."""

from __future__ import annotations

from backend.repositories.paper_repository import PaperRepository, get_paper_repository
from backend.schemas.paradigm import ParadigmClassification


class PaperCoreService:
    """Thin domain service for ``papers`` table metadata updates."""

    def __init__(self, paper_repo: PaperRepository | None = None) -> None:
        self._paper_repo = paper_repo or get_paper_repository()

    async def update_classification(self, paper_id: str, classification: ParadigmClassification) -> None:
        await self._paper_repo.update_classification(paper_id, classification)

    async def update_paths(
        self,
        paper_id: str,
        *,
        graph_path: str | None = None,
        head_path: str | None = None,
        pdf_path: str | None = None,
    ) -> None:
        await self._paper_repo.update_paths(
            paper_id,
            graph_path=graph_path,
            head_path=head_path,
            pdf_path=pdf_path,
        )

    async def update_title(self, paper_id: str, title: str) -> None:
        await self._paper_repo.update_title(paper_id, title)

    async def mark_preview_available(self, paper_id: str) -> None:
        await self._paper_repo.mark_preview_available(paper_id)

    async def get_graph_version(self, paper_id: str) -> str:
        return await self._paper_repo.get_graph_version(paper_id)

    async def update_graph_version(
        self,
        paper_id: str,
        *,
        graph_version: str,
        extractor_config_hash: str,
    ) -> None:
        await self._paper_repo.update_graph_version(
            paper_id,
            graph_version=graph_version,
            extractor_config_hash=extractor_config_hash,
        )
