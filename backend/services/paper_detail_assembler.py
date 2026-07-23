# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Read-side assembler for ``PaperDetail`` (CQRS query path)."""

from __future__ import annotations

import asyncio

from backend.schemas.paper import PaperDetail
from backend.services.head_refine_coordinator import HeadRefineCoordinator
from backend.services.paper_warning_service import PaperWarningService
from backend.services.preview_graph_facade import PreviewGraphFacade


class PaperDetailAssembler:
    """Compose paper metadata with ingest head, preview flag, and warning codes."""

    def __init__(
        self,
        *,
        head_refine: HeadRefineCoordinator,
        warning_service: PaperWarningService,
        preview_facade: PreviewGraphFacade,
    ) -> None:
        self._head_refine = head_refine
        self._warnings = warning_service
        self._preview = preview_facade

    async def assemble(self, paper: PaperDetail, paper_id: str) -> PaperDetail:
        """Hydrate detail fields from disk / pipeline snapshot without mutating core CRUD."""
        # Disk → DB warning sync must finish before warning reads so status/detail stay aligned.
        await self._head_refine.sync_warnings_from_disk(paper_id)
        ingest_head, warning_pair, preview_available = await asyncio.gather(
            self._head_refine.load_head(paper_id),
            self._warnings.get_extract_and_classify(paper_id),
            self._preview.is_available(paper_id),
        )
        extract_warnings, classify_warnings = warning_pair
        return paper.model_copy(
            update={
                "ingest_head": ingest_head,
                "preview_available": paper.preview_available or preview_available,
                "extract_warnings": extract_warnings,
                "classify_warnings": classify_warnings,
            },
        )
