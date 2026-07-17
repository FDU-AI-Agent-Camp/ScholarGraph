# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Facade for ingest head merge (rules + LLM gate)."""

from __future__ import annotations

from functools import lru_cache

from backend.config import Settings, get_settings
from backend.ingest.head_candidates import HeadCandidate
from backend.ingest.head_merge import merge_head_candidates
from backend.schemas.ingest_head import IngestHead


class HeadMergeService:
    """Merge PyMuPDF snippets with async path-B candidate."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def merge(
        self,
        snippets: HeadCandidate,
        path_b: HeadCandidate | None,
        *,
        is_short: bool,
    ) -> IngestHead:
        return await merge_head_candidates(
            snippets,
            path_b,
            is_short=is_short,
            settings=self._settings,
        )


@lru_cache
def get_head_merge_service() -> HeadMergeService:
    return HeadMergeService()
