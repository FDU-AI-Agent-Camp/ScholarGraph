# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Core paper metadata operations backed by ``PaperRepository``."""

from __future__ import annotations

from backend.repositories import run_async
from backend.repositories.paper_repository import PaperRepository, get_paper_repository
from backend.schemas.paradigm import ParadigmClassification


class PaperCoreService:
    """Thin domain service for ``papers`` table metadata updates."""

    def __init__(self, paper_repo: PaperRepository | None = None) -> None:
        self._paper_repo = paper_repo or get_paper_repository()

    async def aupdate_classification(self, paper_id: str, classification: ParadigmClassification) -> None:
        await self._paper_repo.update_classification(paper_id, classification)

    async def aupdate_paths(
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

    async def aupdate_title(self, paper_id: str, title: str) -> None:
        await self._paper_repo.update_title(paper_id, title)

    async def amark_preview_available(self, paper_id: str) -> None:
        await self._paper_repo.mark_preview_available(paper_id)

    async def aget_graph_version(self, paper_id: str) -> str:
        return await self._paper_repo.get_graph_version(paper_id)

    async def aupdate_graph_version(
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

    def update_classification(self, paper_id: str, classification: ParadigmClassification) -> None:
        run_async(self.aupdate_classification(paper_id, classification))

    def update_paths(
        self,
        paper_id: str,
        *,
        graph_path: str | None = None,
        head_path: str | None = None,
        pdf_path: str | None = None,
    ) -> None:
        run_async(
            self.aupdate_paths(
                paper_id,
                graph_path=graph_path,
                head_path=head_path,
                pdf_path=pdf_path,
            ),
        )

    def update_title(self, paper_id: str, title: str) -> None:
        run_async(self.aupdate_title(paper_id, title))

    def mark_preview_available(self, paper_id: str) -> None:
        run_async(self.amark_preview_available(paper_id))

    def get_graph_version(self, paper_id: str) -> str:
        return run_async(self.aget_graph_version(paper_id))

    def update_graph_version(
        self,
        paper_id: str,
        *,
        graph_version: str,
        extractor_config_hash: str,
    ) -> None:
        run_async(
            self.aupdate_graph_version(
                paper_id,
                graph_version=graph_version,
                extractor_config_hash=extractor_config_hash,
            ),
        )
