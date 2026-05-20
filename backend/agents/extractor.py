"""Structured graph extraction (BE-2)."""

from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm


async def extract(full_text: str, paradigm: Paradigm) -> UnifiedPaperGraph:
    """Extract UnifiedPaperGraph from full text."""
    raise NotImplementedError("BE-2: implement in backend/agents/extractor.py")
