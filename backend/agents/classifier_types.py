"""Types for paradigm classification results."""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from backend.schemas.paradigm import ParadigmClassification


class ClassifierProfile(BaseModel):
    """Stage A semantic dehydration output (understand before judging)."""

    goal: str = Field(
        default="",
        description="The phenomenon/problem the paper ultimately tries to explain, derive, solve, or establish.",
    )
    tools: str = Field(
        default="",
        description="Techniques, algorithms, data, or experimental tools used in the paper.",
    )
    domain: str = Field(
        default="",
        description=(
            "Whether the conclusion advances a technology/algorithm itself, "
            "or solves/illuminates a specific historical/social/real-world factual question."
        ),
    )


@dataclass(frozen=True)
class ClassifyResult:
    """Classifier output plus optional degrade warnings."""

    classification: ParadigmClassification
    warnings: list[str] = field(default_factory=list)
