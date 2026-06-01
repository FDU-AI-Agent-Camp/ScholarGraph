"""Structured graph extraction (BE-2)."""

from backend.agents.mock_agents import mock_extract
from backend.config import get_settings
from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm


async def extract(full_text: str, paradigm: Paradigm) -> UnifiedPaperGraph:
    """Extract UnifiedPaperGraph from full text."""
    if get_settings().is_llm_mock:
        return mock_extract(full_text, paradigm)
    raise NotImplementedError("BE-2: implement in backend/agents/extractor.py")
