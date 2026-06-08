"""Types for graph extraction results."""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.schemas.graph import UnifiedPaperGraph


@dataclass(frozen=True)
class ExtractResult:
    """Graph extraction output plus optional degrade warnings."""

    graph: UnifiedPaperGraph
    warnings: list[str] = field(default_factory=list)
