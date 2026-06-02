"""Paradigm classification schema shared by agent and API layers."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Paradigm(str, Enum):
    """Supported ScholarGraph paper paradigms."""

    STEM = "STEM"
    HSS = "HSS"


class ParadigmClassification(BaseModel):
    """Stable JSON output of the paradigm classifier."""

    model_config = ConfigDict(use_enum_values=True)

    paradigm: Paradigm
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1)

