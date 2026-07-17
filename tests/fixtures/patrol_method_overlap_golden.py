# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Load and validate patrol method-overlap golden pairs (topology blueprint v2)."""

from __future__ import annotations

import json
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from backend.schemas.graph import GraphEdge, GraphNode, NodeType, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm
from backend.schemas.patrol import MethodOverlapPoint, OverlapType, PatrolInsight, PatrolInsightStatus
from pydantic import BaseModel, Field, model_validator

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN_SET_PATH = _REPO_ROOT / "data" / "patrol_method_overlap_golden.json"
_SCHEMA_VERSION = 3
_EXPECTED_PAIR_COUNT = 3
_BASELINE_ARCHETYPES = frozenset(
    {
        "SYNONYM_TRUE_POSITIVE",
        "CORRELATED_FALSE_POSITIVE",
        "LITERAL_TRUE_POSITIVE",
    },
)


class GoldenArchetype(StrEnum):
    SYNONYM_TRUE_POSITIVE = "SYNONYM_TRUE_POSITIVE"
    CORRELATED_FALSE_POSITIVE = "CORRELATED_FALSE_POSITIVE"
    LITERAL_TRUE_POSITIVE = "LITERAL_TRUE_POSITIVE"


class GoldenExpectedStatus(StrEnum):
    READY = "READY"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class GoldenExpectedMatchType(StrEnum):
    LITERAL = "LITERAL"
    SEMANTIC = "SEMANTIC"


class GoldenEntitySpec(BaseModel):
    node_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    data: dict[str, str] = Field(default_factory=dict)


class TopologyNeighborSpec(BaseModel):
    node_id: str = Field(min_length=1)
    node_type: Literal["Dataset", "ResearchQuestion"]
    label: str = Field(min_length=1)
    edge_type: Literal["EVALUATED_ON", "ADDRESSES"] = "EVALUATED_ON"
    attach_to_method: bool = True


class GoldenPaperBlueprint(BaseModel):
    method: GoldenEntitySpec
    dataset: GoldenEntitySpec | None = None
    research_question: GoldenEntitySpec | None = None
    topology_neighbors: list[TopologyNeighborSpec] = Field(default_factory=list)


class SharedTopologySpec(BaseModel):
    resonant_dataset_labels: list[str] = Field(default_factory=list)
    notes: str | None = None


class DriftGuardSpec(BaseModel):
    """Semantic drift guard for false-positive archetypes (live regression only)."""

    enabled: bool = True
    require_below_semantic_threshold: bool = True


class GoldenExpectationBlock(BaseModel):
    expected_status: GoldenExpectedStatus
    expected_match_type: GoldenExpectedMatchType | None = None
    expected_overlap_label: str | None = None
    theta_min: float | None = Field(default=None, ge=0.0, le=1.0)
    drift_guard: DriftGuardSpec | None = None

    @model_validator(mode="after")
    def validate_ready_requires_match_type(self) -> GoldenExpectationBlock:
        if self.expected_status == GoldenExpectedStatus.READY and self.expected_match_type is None:
            msg = "READY cases must declare expected_match_type (LITERAL or SEMANTIC)"
            raise ValueError(msg)
        return self


class MethodOverlapGoldenPair(BaseModel):
    id: str = Field(min_length=1)
    priority: Literal["P0", "P1", "P2"] = "P0"
    issue_id: str | None = None
    archetype: GoldenArchetype
    paradigm: Literal["STEM"]
    paper_a_id: str = Field(min_length=1)
    paper_b_id: str = Field(min_length=1)
    paper_a: GoldenPaperBlueprint
    paper_b: GoldenPaperBlueprint
    shared_topology: SharedTopologySpec
    expectation: GoldenExpectationBlock
    rationale: str = Field(min_length=1)


class GoldenConfigSnapshot(BaseModel):
    """Pinned Patrol runtime config recorded in the method_overlap golden header."""

    patrol_semantic_threshold: float = Field(ge=0.0, le=1.0)
    embedding_model: str = Field(min_length=1)
    enable_patrol_semantic_path: bool = True
    snapshot_recorded_at: str | None = None
    notes: str | None = None


class MethodOverlapGoldenSet(BaseModel):
    schema_version: int
    dataset_id: str
    description: str
    owner: str | None = None
    config_snapshot: GoldenConfigSnapshot
    baseline_matrix: list[str]
    pairs: list[MethodOverlapGoldenPair]

    @model_validator(mode="after")
    def validate_baseline(self) -> MethodOverlapGoldenSet:
        if self.schema_version != _SCHEMA_VERSION:
            msg = f"expected schema_version={_SCHEMA_VERSION}, got {self.schema_version}"
            raise ValueError(msg)

        if len(self.pairs) != _EXPECTED_PAIR_COUNT:
            msg = f"golden set must contain exactly {_EXPECTED_PAIR_COUNT} baseline pairs"
            raise ValueError(msg)

        ids = [pair.id for pair in self.pairs]
        if len(ids) != len(set(ids)):
            raise ValueError("golden pair ids must be unique")

        archetypes = {pair.archetype.value for pair in self.pairs}
        if archetypes != set(self.baseline_matrix) or archetypes != _BASELINE_ARCHETYPES:
            msg = f"baseline_matrix must cover {_BASELINE_ARCHETYPES}, got {archetypes}"
            raise ValueError(msg)

        nb_lr = next(pair for pair in self.pairs if pair.archetype == GoldenArchetype.CORRELATED_FALSE_POSITIVE)
        if nb_lr.issue_id != "NB_LR_FALSE_POSITIVE":
            msg = "CORRELATED_FALSE_POSITIVE case must set issue_id=NB_LR_FALSE_POSITIVE"
            raise ValueError(msg)
        if nb_lr.expectation.drift_guard is None or not nb_lr.expectation.drift_guard.enabled:
            msg = "CORRELATED_FALSE_POSITIVE case must enable drift_guard"
            raise ValueError(msg)

        return self


@lru_cache(maxsize=1)
def load_method_overlap_golden_set() -> MethodOverlapGoldenSet:
    """Load and validate ``data/patrol_method_overlap_golden.json``."""
    raw = json.loads(_GOLDEN_SET_PATH.read_text(encoding="utf-8"))
    return MethodOverlapGoldenSet.model_validate(raw)


def golden_set_path() -> Path:
    return _GOLDEN_SET_PATH


def _build_paper_graph(paper_id: str, blueprint: GoldenPaperBlueprint) -> UnifiedPaperGraph:
    """Materialize an in-memory STEM subgraph from a golden paper blueprint."""
    nodes: list[GraphNode] = [
        GraphNode(
            id=blueprint.method.node_id,
            label=blueprint.method.label,
            type=NodeType.METHOD,
            data=blueprint.method.data,
        ),
    ]
    edges: list[GraphEdge] = []
    edge_counter = 0

    if blueprint.dataset is not None:
        nodes.append(
            GraphNode(
                id=blueprint.dataset.node_id,
                label=blueprint.dataset.label,
                type=NodeType.DATASET,
                data=blueprint.dataset.data,
            ),
        )
        edge_counter += 1
        edges.append(
            GraphEdge(
                id=f"e_dataset_{edge_counter}",
                source=blueprint.dataset.node_id,
                target=blueprint.method.node_id,
                label="EVALUATED_ON",
                type="EVALUATED_ON",
            ),
        )

    if blueprint.research_question is not None:
        nodes.append(
            GraphNode(
                id=blueprint.research_question.node_id,
                label=blueprint.research_question.label,
                type=NodeType.RESEARCH_QUESTION,
                data=blueprint.research_question.data,
            ),
        )
        edge_counter += 1
        edges.append(
            GraphEdge(
                id=f"e_rq_{edge_counter}",
                source=blueprint.method.node_id,
                target=blueprint.research_question.node_id,
                label="ADDRESSES",
                type="ADDRESSES",
            ),
        )

    declared_neighbor_ids = {neighbor.node_id for neighbor in blueprint.topology_neighbors}
    graph_node_ids = {node.id for node in nodes}
    if not declared_neighbor_ids.issubset(graph_node_ids):
        missing = declared_neighbor_ids - graph_node_ids
        msg = f"topology_neighbors reference unknown node ids for {paper_id}: {sorted(missing)}"
        raise ValueError(msg)

    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.STEM,
        nodes=nodes,
        edges=edges,
    )


def build_graphs_for_pair(pair: MethodOverlapGoldenPair) -> dict[str, UnifiedPaperGraph]:
    """Build self-contained in-memory subgraphs for a golden pair."""
    return {
        pair.paper_a_id: _build_paper_graph(pair.paper_a_id, pair.paper_a),
        pair.paper_b_id: _build_paper_graph(pair.paper_b_id, pair.paper_b),
    }


def hydrate_patrol_graph_pair(pair: MethodOverlapGoldenPair) -> dict[str, UnifiedPaperGraph]:
    """Alias for live runner graph hydration from topology blueprint."""
    return build_graphs_for_pair(pair)


def _method_overlap_points(insight: PatrolInsight) -> list[MethodOverlapPoint]:
    points: list[MethodOverlapPoint] = []
    for point in insight.structured_points:
        if isinstance(point, MethodOverlapPoint):
            points.append(point)
    return points


def evaluate_method_overlap_golden_pair(
    insight: PatrolInsight,
    pair: MethodOverlapGoldenPair,
) -> tuple[bool, str]:
    """Return (passed, detail) against the pair expectation block."""
    expected = pair.expectation
    expected_status = (
        PatrolInsightStatus.READY
        if expected.expected_status == GoldenExpectedStatus.READY
        else (PatrolInsightStatus.INSUFFICIENT_DATA)
    )

    if insight.status != expected_status:
        return False, f"status={insight.status.value}, expected={expected.expected_status.value}"

    if expected_status == PatrolInsightStatus.INSUFFICIENT_DATA:
        if insight.structured_points:
            return False, f"expected no structured_points, got {len(insight.structured_points)}"
        return True, "topology veto / no overlap as expected"

    method_points = [point for point in _method_overlap_points(insight) if point.overlap_type == OverlapType.METHOD]
    if not method_points:
        method_points = _method_overlap_points(insight)
    if not method_points:
        return False, "READY expected but structured_points empty"

    primary = method_points[0]
    if expected.expected_overlap_label is not None:
        if primary.overlap_label != expected.expected_overlap_label:
            return (
                False,
                f"overlap_label={primary.overlap_label!r}, expected={expected.expected_overlap_label!r}",
            )

    if expected.expected_match_type is not None:
        actual_match = primary.match_type
        expected_match = expected.expected_match_type.value.lower()
        if actual_match != expected_match:
            return False, f"match_type={actual_match}, expected={expected_match}"

    if expected.theta_min is not None:
        score = primary.overlap_score
        if score is None or score < expected.theta_min:
            return False, f"overlap_score={score}, theta_min={expected.theta_min}"

    return True, (f"status=ready, match_type={primary.match_type}, overlap_score={primary.overlap_score}")
