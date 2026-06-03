"""Paradigm classification schemas."""

from enum import StrEnum

from pydantic import BaseModel, Field


class Paradigm(StrEnum):
    STEM = "STEM"
    HSS = "HSS"


class ParadigmClassification(BaseModel):
    """Stable JSON output of the paradigm classifier."""

    paradigm: Paradigm
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1)
