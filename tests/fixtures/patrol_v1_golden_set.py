# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Load and evaluate Patrol V1 golden cases (lens_clash / contradiction)."""

from __future__ import annotations

import json
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from backend.patrol.contradiction import build_contradiction_insight
from backend.patrol.lens_clash import build_lens_clash_insight
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm
from backend.schemas.patrol import ContradictionPoint, LensClashPoint, PatrolInsight, PatrolMode
from pydantic import BaseModel, Field, model_validator

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN_SET_PATH = _REPO_ROOT / "data" / "patrol_v1_golden_set.json"
_EXPECTED_CASE_COUNT = 8


class V1GoldenExpectation(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


class V1PaperSpec(BaseModel):
    lens_label: str | None = None
    thesis_label: str | None = None
    sub_arguments: list[str] = Field(default_factory=list)


class V1ExpectedOutcome(BaseModel):
    insight_null: bool = False
    status: Literal["ready", "insufficient_data"] | None = None
    clash_aspect: str | None = None
    conflict_type: str | None = None
    has_contradiction: bool | None = None


class PatrolV1GoldenCase(BaseModel):
    id: str = Field(min_length=1)
    mode: Literal["lens_clash", "contradiction"]
    expectation: V1GoldenExpectation
    paper_a_id: str
    paper_b_id: str
    rationale: str = Field(min_length=1)
    paper_a: V1PaperSpec
    paper_b: V1PaperSpec
    expected: V1ExpectedOutcome


class PatrolV1GoldenSet(BaseModel):
    schema_version: int
    dataset_id: str
    description: str
    owner: str | None = None
    cases: list[PatrolV1GoldenCase]

    @model_validator(mode="after")
    def validate_distribution(self) -> PatrolV1GoldenSet:
        if len(self.cases) != _EXPECTED_CASE_COUNT:
            msg = f"V1 golden set must contain exactly {_EXPECTED_CASE_COUNT} cases"
            raise ValueError(msg)
        ids = [case.id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("V1 golden case ids must be unique")
        return self


@lru_cache(maxsize=1)
def load_patrol_v1_golden_set() -> PatrolV1GoldenSet:
    raw = json.loads(_GOLDEN_SET_PATH.read_text(encoding="utf-8"))
    return PatrolV1GoldenSet.model_validate(raw)


def golden_v1_set_path() -> Path:
    return _GOLDEN_SET_PATH


def _build_graph(paper_id: str, spec: V1PaperSpec) -> UnifiedPaperGraph:
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    if spec.lens_label:
        nodes.append(GraphNode(id=f"{paper_id}-lens", label=spec.lens_label, type="AnalyticalLens", data={}))
    if spec.thesis_label:
        thesis_id = f"{paper_id}-thesis"
        nodes.append(GraphNode(id=thesis_id, label=spec.thesis_label, type="Thesis", data={}))
        for index, sub_label in enumerate(spec.sub_arguments, start=1):
            sub_id = f"{paper_id}-sub-{index}"
            nodes.append(GraphNode(id=sub_id, label=sub_label, type="SubArgument", data={}))
            edges.append(
                GraphEdge(
                    id=f"{paper_id}-edge-{index}",
                    source=sub_id,
                    target=thesis_id,
                    label="SUB_ARGUMENT_OF",
                    type="SUB_ARGUMENT_OF",
                )
            )
    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=nodes,
        edges=edges,
    )


def build_graphs_for_v1_case(case: PatrolV1GoldenCase) -> dict[str, UnifiedPaperGraph]:
    return {
        case.paper_a_id: _build_graph(case.paper_a_id, case.paper_a),
        case.paper_b_id: _build_graph(case.paper_b_id, case.paper_b),
    }


async def evaluate_v1_golden_case(case: PatrolV1GoldenCase) -> tuple[bool, str]:
    graphs = build_graphs_for_v1_case(case)
    paper_ids = [case.paper_a_id, case.paper_b_id]
    insight: PatrolInsight | None
    if case.mode == "lens_clash":
        insight = await build_lens_clash_insight(graphs, paper_ids)
    else:
        insight = await build_contradiction_insight(graphs, paper_ids)

    expected = case.expected
    if expected.insight_null:
        if insight is not None:
            return False, "expected no insight"
        return True, "insight_null"

    if insight is None:
        return False, "expected insight but got None"

    if expected.status is not None and insight.status.value != expected.status:
        return False, f"status={insight.status.value} expected={expected.status}"

    if case.mode == "lens_clash":
        if not insight.structured_points:
            return False, "missing structured_points"
        point = insight.structured_points[0]
        if not isinstance(point, LensClashPoint):
            return False, "expected LensClashPoint"
        if expected.clash_aspect is not None and point.clash_aspect != expected.clash_aspect:
            return False, f"clash_aspect={point.clash_aspect} expected={expected.clash_aspect}"
    else:
        if expected.has_contradiction is not None and insight.has_contradiction != expected.has_contradiction:
            return (
                False,
                f"has_contradiction={insight.has_contradiction} expected={expected.has_contradiction}",
            )
        if expected.status == "ready":
            if not insight.structured_points:
                return False, "missing structured_points"
            point = insight.structured_points[0]
            if not isinstance(point, ContradictionPoint):
                return False, "expected ContradictionPoint"
            if expected.conflict_type is not None and point.conflict_type != expected.conflict_type:
                return False, f"conflict_type={point.conflict_type} expected={expected.conflict_type}"

    return True, "ok"


def patrol_mode_from_v1_case(case: PatrolV1GoldenCase) -> PatrolMode:
    return PatrolMode(case.mode)
