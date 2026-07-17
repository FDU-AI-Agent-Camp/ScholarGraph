# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Unified paper graph schema with paradigm-specific validation (G6 via GraphStore)."""

import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.schemas.paradigm import Paradigm

# Dynamic relation verbs invented by the LLM must use SCREAMING_SNAKE_CASE.
_DYNAMIC_EDGE_TYPE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")

# Explicitly banned edge types even if they match the dynamic pattern.
_FORBIDDEN_EDGE_TYPES = frozenset({"SUPPORTED_BY"})


class NodeType(StrEnum):
    """Node labels exposed to graph consumers and G6."""

    RESEARCH_QUESTION = "ResearchQuestion"
    METHOD = "Method"
    DATASET = "Dataset"
    METRIC = "Metric"
    BASELINE = "Baseline"
    EXPERIMENT = "Experiment"
    CLAIM = "Claim"
    EVIDENCE = "Evidence"
    FINDING = "Finding"
    THESIS = "Thesis"
    SUB_ARGUMENT = "SubArgument"
    ANALYTICAL_LENS = "AnalyticalLens"
    INTELLECTUAL_CONTEXT = "IntellectualContext"
    OBJECT_OR_DATA = "ObjectOrData"


STEM_NODE_TYPES = frozenset(
    {
        NodeType.RESEARCH_QUESTION,
        NodeType.METHOD,
        NodeType.DATASET,
        NodeType.METRIC,
        NodeType.BASELINE,
        NodeType.EXPERIMENT,
        NodeType.CLAIM,
        NodeType.EVIDENCE,
        NodeType.FINDING,
    }
)
HSS_NODE_TYPES = frozenset(
    {
        NodeType.THESIS,
        NodeType.SUB_ARGUMENT,
        NodeType.ANALYTICAL_LENS,
        NodeType.INTELLECTUAL_CONTEXT,
        NodeType.OBJECT_OR_DATA,
        NodeType.CLAIM,
        NodeType.EVIDENCE,
    }
)
STEM_EDGE_TYPES = frozenset(
    {
        "ADDRESSES",
        "USES_METHOD",
        "EVALUATED_ON",
        "MEASURED_BY",
        "COMPARES_TO",
        "SUPPORTS",
        "PRODUCES",
        "RELATES_TO",
        # NOTE: SUPPORTED_BY was intentionally removed to keep the evidence flow
        # unidirectional: Evidence --SUPPORTS--> Claim. This avoids LLM confusion
        # over which node carries the textual anchor (source_span).
    }
)
HSS_EDGE_TYPES = frozenset(
    {
        "CHALLENGES",
        "SUB_ARGUMENT_OF",
        "EXAMINES_THROUGH",
        "SUPPORTS",
        "CONTEXTUALIZES",
        "RELATES_TO",
        "LENS_OF",
        "INFORMS",
        "REF",
    }
)


class GraphNode(BaseModel):
    """A graph node compatible with the V1 OpenAPI GraphNode schema."""

    model_config = ConfigDict(use_enum_values=True)

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    type: NodeType
    data: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    """A graph edge compatible with the V1 OpenAPI GraphEdge schema."""

    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    label: str = Field(min_length=1)
    type: str = Field(min_length=1)
    rationale: str | None = Field(default=None, description="Logical justification for the relationship.")
    source_span: str | None = Field(
        default=None,
        description="Verbatim textual evidence from the paper supporting this relation.",
    )
    confidence: Literal["HIGH", "MEDIUM", "LOW"] | None = Field(default=None, description="Confidence tier.")
    data: dict[str, Any] = Field(default_factory=dict)


class UnifiedPaperGraph(BaseModel):
    """Single-paper logic graph used by extraction, storage, QA, and patrol modules."""

    paper_id: str = Field(min_length=1)
    title: str | None = None
    paradigm: Paradigm
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    summary: str | None = None

    @model_validator(mode="after")
    def validate_graph_consistency(self) -> "UnifiedPaperGraph":
        """Reject duplicate ids, dangling edges, and paradigm-forbidden node/edge types."""

        node_ids = [node.id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Graph node ids must be unique.")
        edge_ids = [edge.id for edge in self.edges]
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("Graph edge ids must be unique.")
        node_id_set = set(node_ids)
        for edge in self.edges:
            if edge.source not in node_id_set or edge.target not in node_id_set:
                raise ValueError(f"Graph edge {edge.id} references missing node.")

        allowed_node_types = HSS_NODE_TYPES if self.paradigm == Paradigm.HSS else STEM_NODE_TYPES
        forbidden_nodes = [node.type for node in self.nodes if node.type not in allowed_node_types]
        if forbidden_nodes:
            raise ValueError(f"{self.paradigm} graph contains forbidden node types: {forbidden_nodes}")

        # Predefined edge types are preferred, but the LLM may invent specific verbs
        # in SCREAMING_SNAKE_CASE when none of the predefined types fit.
        allowed_edge_types = HSS_EDGE_TYPES if self.paradigm == Paradigm.HSS else STEM_EDGE_TYPES
        invalid_edges = [
            edge.type
            for edge in self.edges
            if edge.type in _FORBIDDEN_EDGE_TYPES
            or (edge.type not in allowed_edge_types and not _DYNAMIC_EDGE_TYPE_PATTERN.match(edge.type))
        ]
        if invalid_edges:
            raise ValueError(
                f"{self.paradigm} graph contains forbidden edge types: {invalid_edges}. "
                "Use a predefined type or a SCREAMING_SNAKE_CASE verb."
            )
        return self
