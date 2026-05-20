"""Paradigm classifier (BE-2)."""

from backend.schemas.paradigm import ParadigmClassification


async def classify(classifier_input: str) -> ParadigmClassification:
    """Classify paper as STEM or HSS."""
    raise NotImplementedError("BE-2: implement in backend/agents/classifier.py")
