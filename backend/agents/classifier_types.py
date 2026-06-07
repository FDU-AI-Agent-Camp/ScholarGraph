"""Types for paradigm classification results."""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.schemas.paradigm import ParadigmClassification


@dataclass(frozen=True)
class ClassifyResult:
    """Classifier output plus optional degrade warnings."""

    classification: ParadigmClassification
    warnings: list[str] = field(default_factory=list)
