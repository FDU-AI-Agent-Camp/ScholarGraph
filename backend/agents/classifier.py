"""Paradigm classifier (BE-2)."""

from backend.agents.mock_agents import mock_classify
from backend.config import get_settings
from backend.schemas.paradigm import ParadigmClassification


async def classify(classifier_input: str) -> ParadigmClassification:
    """Classify paper as STEM or HSS."""
    if get_settings().is_llm_mock:
        return mock_classify(classifier_input)
    raise NotImplementedError("BE-2: implement in backend/agents/classifier.py")
