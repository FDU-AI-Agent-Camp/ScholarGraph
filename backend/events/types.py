"""Persistence-related event type definitions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from backend.schemas.graph import UnifiedPaperGraph


class EventType(StrEnum):
    PIPELINE_FINALIZED = "pipeline_finalized"


@dataclass(frozen=True)
class PipelineFinalized:
    """Emitted after graph persistence and paper status reaches a ready terminal state.

    Frozen contract (do not rename or remove fields without a version bump):
    - ``paper_id``: finalized paper identifier
    - ``full_text``: PyMuPDF-extracted body used for chunk indexing
    - ``graph``: persisted ``UnifiedPaperGraph`` snapshot
    """

    paper_id: str
    full_text: str
    graph: UnifiedPaperGraph

    @property
    def event_type(self) -> EventType:
        return EventType.PIPELINE_FINALIZED
