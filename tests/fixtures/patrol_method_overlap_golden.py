"""Load and validate patrol method-overlap golden pairs."""

from __future__ import annotations

import json
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from backend.schemas.graph import UnifiedPaperGraph
from pydantic import BaseModel, Field, model_validator
from tests.helpers.patrol_graphs import (
    build_stem_graph_with_method_dataset,
    build_stem_graph_with_method_dataset_rq,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN_SET_PATH = _REPO_ROOT / "data" / "patrol_method_overlap_golden.json"
_EXPECTED_PAIR_COUNT = 4
_EXPECTED_POSITIVE_COUNT = 2
_EXPECTED_NEGATIVE_COUNT = 2


class MethodOverlapGoldenExpectation(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


class MethodOverlapPaperSpec(BaseModel):
    method_label: str = Field(min_length=1)
    dataset_label: str = Field(min_length=1)
    method_data: dict[str, str] | None = None
    dataset_data: dict[str, str] | None = None
    question_label: str | None = None


class MethodOverlapGoldenPair(BaseModel):
    id: str = Field(min_length=1)
    paradigm: Literal["STEM"]
    expectation: MethodOverlapGoldenExpectation
    paper_a_id: str = Field(min_length=1)
    paper_b_id: str = Field(min_length=1)
    paper_a: MethodOverlapPaperSpec
    paper_b: MethodOverlapPaperSpec
    rationale: str = Field(min_length=1)


class MethodOverlapGoldenSet(BaseModel):
    schema_version: int
    dataset_id: str
    description: str
    owner: str | None = None
    pairs: list[MethodOverlapGoldenPair]

    @model_validator(mode="after")
    def validate_distribution(self) -> MethodOverlapGoldenSet:
        if len(self.pairs) != _EXPECTED_PAIR_COUNT:
            msg = f"golden set must contain exactly {_EXPECTED_PAIR_COUNT} pairs"
            raise ValueError(msg)

        ids = [pair.id for pair in self.pairs]
        if len(ids) != len(set(ids)):
            raise ValueError("golden pair ids must be unique")

        positive_count = sum(1 for pair in self.pairs if pair.expectation == MethodOverlapGoldenExpectation.POSITIVE)
        negative_count = sum(1 for pair in self.pairs if pair.expectation == MethodOverlapGoldenExpectation.NEGATIVE)
        if positive_count != _EXPECTED_POSITIVE_COUNT or negative_count != _EXPECTED_NEGATIVE_COUNT:
            msg = (
                f"expected positive={_EXPECTED_POSITIVE_COUNT} negative={_EXPECTED_NEGATIVE_COUNT}, "
                f"got positive={positive_count} negative={negative_count}"
            )
            raise ValueError(msg)

        return self


@lru_cache(maxsize=1)
def load_method_overlap_golden_set() -> MethodOverlapGoldenSet:
    """Load and validate ``data/patrol_method_overlap_golden.json``."""
    raw = json.loads(_GOLDEN_SET_PATH.read_text(encoding="utf-8"))
    return MethodOverlapGoldenSet.model_validate(raw)


def golden_set_path() -> Path:
    return _GOLDEN_SET_PATH


def build_graphs_for_pair(pair: MethodOverlapGoldenPair) -> dict[str, UnifiedPaperGraph]:
    """Materialize UnifiedPaperGraph dict for a golden pair."""
    graphs: dict[str, UnifiedPaperGraph] = {}

    for paper_id, spec in (
        (pair.paper_a_id, pair.paper_a),
        (pair.paper_b_id, pair.paper_b),
    ):
        if spec.question_label:
            graphs[paper_id] = build_stem_graph_with_method_dataset_rq(
                paper_id,
                method_label=spec.method_label,
                method_data=spec.method_data,
                dataset_label=spec.dataset_label,
                dataset_data=spec.dataset_data,
                question_label=spec.question_label,
            )
        else:
            graphs[paper_id] = build_stem_graph_with_method_dataset(
                paper_id,
                method_label=spec.method_label,
                method_data=spec.method_data,
                dataset_label=spec.dataset_label,
                dataset_data=spec.dataset_data,
            )

    return graphs
