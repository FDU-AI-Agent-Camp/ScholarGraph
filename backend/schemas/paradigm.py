"""Paradigm classification schemas."""

from enum import StrEnum

from pydantic import BaseModel, Field


class Paradigm(StrEnum):
    STEM = "STEM"
    HSS = "HSS"


class ParadigmClassification(BaseModel):
    paradigm: Paradigm
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
