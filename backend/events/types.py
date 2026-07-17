# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Persistence-related event type definitions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.paper import PaperStatus


class EventType(StrEnum):
    PIPELINE_FINALIZED = "pipeline_finalized"
    RAG_INDEXED = "rag_indexed"


@dataclass(frozen=True)
class PipelineFinalized:
    """Emitted after graph persistence; status is ``indexing`` until RAG promotes ready.

    Frozen contract (do not rename or remove fields without a version bump):
    - ``paper_id``: finalized paper identifier
    - ``full_text``: PyMuPDF-extracted body used for chunk indexing
    - ``graph``: persisted ``UnifiedPaperGraph`` snapshot
    - ``page_break_offsets``: normalized-text cumulative offsets per page break (optional)
    - ``terminal_status``: status to apply after successful RAG index (ready / ready_with_warnings)
    """

    paper_id: str
    full_text: str
    graph: UnifiedPaperGraph
    page_break_offsets: list[int] | None = None
    terminal_status: PaperStatus = PaperStatus.READY
    warning_message: str | None = None

    @property
    def event_type(self) -> EventType:
        return EventType.PIPELINE_FINALIZED


@dataclass(frozen=True)
class RagIndexed:
    """Emitted after VectorStore indexing completes for a finalized paper (P10 chain)."""

    paper_id: str
    success: bool
    terminal_status: PaperStatus

    @property
    def event_type(self) -> EventType:
        return EventType.RAG_INDEXED
