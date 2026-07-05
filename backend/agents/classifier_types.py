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


class CoreContributionAnalysis(BaseModel):
    """Stage B core-contribution interrogation output."""

    core_contribution_summary: str = Field(
        default="",
        description="Restatement of the paper's core intellectual contribution in one sentence.",
    )
    substitution_test: str = Field(
        default="",
        description="Result of the substitution test and its implied direction (STEM or HSS).",
    )
    target_journal_test: str = Field(
        default="",
        description="Whether the target journal would accept the paper primarily for the method or the finding.",
    )


@dataclass(frozen=True)
class ClassifyResult:
    """Classifier output plus optional degrade warnings."""

    classification: ParadigmClassification
    warnings: list[str] = field(default_factory=list)
