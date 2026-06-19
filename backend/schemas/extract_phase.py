"""Intermediate schemas for two-phase graph extraction (v2)."""

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.schemas.graph import HSS_EDGE_TYPES, HSS_NODE_TYPES, STEM_EDGE_TYPES, STEM_NODE_TYPES
from backend.schemas.paradigm import Paradigm

logger = logging.getLogger(__name__)

MAX_NODE_LABEL_LENGTH = 120
MAX_EDGE_LABEL_LENGTH = 120
MAX_SOURCE_SPAN_LENGTH = 500
TRUNCATION_SUFFIX = "..."


class ExtractedNode(BaseModel):
    """A node produced by Stage 1 (node extraction)."""

    model_config = ConfigDict(use_enum_values=True)

    id: str = Field(min_length=1, description="Unique node identifier.")
    label: str = Field(
        min_length=1,
        max_length=120,
        description="Concise phrase faithful to the paper text.",
    )
    type: str = Field(min_length=1, description="Node type from the paradigm whitelist.")
    source_span: str | None = Field(
        default=None,
        max_length=500,
        description="Textual evidence from the paper supporting this node.",
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("label", mode="before")
    @classmethod
    def _truncate_label(cls, value: str) -> str:
        """Avoid hard failures when the LLM emits an overly long label."""
        return _smart_truncate(value, MAX_NODE_LABEL_LENGTH, "node.label")

    @field_validator("source_span", mode="before")
    @classmethod
    def _truncate_source_span(cls, value: str | None) -> str | None:
        """Avoid hard failures when the LLM emits an overly long source span."""
        return _smart_truncate_optional(value, MAX_SOURCE_SPAN_LENGTH, "node.source_span")


class ExtractedEdge(BaseModel):
    """An edge produced by Stage 2 (edge extraction)."""

    id: str = Field(min_length=1, description="Unique edge identifier.")
    source: str = Field(min_length=1, description="Source node id.")
    target: str = Field(min_length=1, description="Target node id.")
    label: str = Field(min_length=1, max_length=MAX_EDGE_LABEL_LENGTH)
    type: str = Field(min_length=1, description="Edge type from the paradigm whitelist.")
    source_span: str | None = Field(
        default=None,
        max_length=MAX_SOURCE_SPAN_LENGTH,
        description="Textual evidence supporting this relation.",
    )
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("label", mode="before")
    @classmethod
    def _truncate_label(cls, value: str) -> str:
        """Avoid hard failures when the LLM emits an overly long edge label."""
        return _smart_truncate(value, MAX_EDGE_LABEL_LENGTH, "edge.label")

    @field_validator("source_span", mode="before")
    @classmethod
    def _truncate_source_span(cls, value: str | None) -> str | None:
        """Avoid hard failures when the LLM emits an overly long source span."""
        return _smart_truncate_optional(value, MAX_SOURCE_SPAN_LENGTH, "edge.source_span")


def _smart_truncate(value: str, max_length: int, field_name: str) -> str:
    """Truncate ``value`` to ``max_length`` with an ellipsis suffix and log.

    Keeps the original when it already fits. The suffix is included in the
    final length budget so the result never exceeds ``max_length``.
    """
    if not isinstance(value, str):
        return value
    if len(value) <= max_length:
        return value
    truncated = value[: max_length - len(TRUNCATION_SUFFIX)] + TRUNCATION_SUFFIX
    logger.warning(
        "extract_field_truncated",
        extra={"field": field_name, "original_length": len(value), "max_length": max_length},
    )
    return truncated


def _smart_truncate_optional(value: str | None, max_length: int, field_name: str) -> str | None:
    """Optional variant of :func:`_smart_truncate`."""
    if value is None:
        return None
    return _smart_truncate(value, max_length, field_name)


class ExtractedNodeList(BaseModel):
    """Stage 1 output: extracted nodes validated against the paradigm whitelist."""

    paradigm: Paradigm
    nodes: list[ExtractedNode] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_node_consistency(self) -> "ExtractedNodeList":
        """Enforce unique ids and paradigm-specific node types."""
        ids = [node.id for node in self.nodes]
        seen: set[str] = set()
        duplicates = [nid for nid in ids if nid in seen or seen.add(nid)]
        if duplicates:
            raise ValueError(f"Duplicate node ids: {duplicates}")

        allowed = HSS_NODE_TYPES if self.paradigm == Paradigm.HSS else STEM_NODE_TYPES
        allowed_values = {t.value for t in allowed}
        forbidden = [node.type for node in self.nodes if node.type not in allowed_values]
        if forbidden:
            raise ValueError(f"{self.paradigm.value} graph contains forbidden node types: {forbidden}")
        return self


class ExtractedEdgeList(BaseModel):
    """Stage 2 output: extracted edges validated against available nodes."""

    paradigm: Paradigm
    edges: list[ExtractedEdge]
    node_ids: list[str] = Field(
        default_factory=list,
        description="Available node ids that edges may reference.",
    )

    @model_validator(mode="after")
    def validate_edge_consistency(self) -> "ExtractedEdgeList":
        """Enforce unique ids, valid edge types, and dangling-free references."""
        ids = [edge.id for edge in self.edges]
        seen: set[str] = set()
        duplicates = [eid for eid in ids if eid in seen or seen.add(eid)]
        if duplicates:
            raise ValueError(f"Duplicate edge ids: {duplicates}")

        allowed = HSS_EDGE_TYPES if self.paradigm == Paradigm.HSS else STEM_EDGE_TYPES
        forbidden = [edge.type for edge in self.edges if edge.type not in allowed]
        if forbidden:
            raise ValueError(f"{self.paradigm.value} graph contains forbidden edge types: {forbidden}")

        if self.node_ids:
            node_id_set = set(self.node_ids)
            dangling = [
                edge.id for edge in self.edges if edge.source not in node_id_set or edge.target not in node_id_set
            ]
            if dangling:
                raise ValueError(f"Edges reference missing nodes: {dangling}")
        return self


class ExtractedGraph(BaseModel):
    """Combined Stage 1 + Stage 2 output, ready to become UnifiedPaperGraph."""

    paper_id: str = Field(min_length=1)
    title: str | None = None
    paradigm: Paradigm
    nodes: list[ExtractedNode]
    edges: list[ExtractedEdge]
    summary: str | None = None

    @model_validator(mode="after")
    def validate_graph_consistency(self) -> "ExtractedGraph":
        """Final safety net: ids, references, and paradigm whitelists."""
        node_ids = {node.id for node in self.nodes}

        ids = [node.id for node in self.nodes]
        if len(ids) != len(node_ids):
            seen: set[str] = set()
            duplicates = [nid for nid in ids if nid in seen or seen.add(nid)]
            raise ValueError(f"Duplicate node ids: {duplicates}")

        edge_ids = [edge.id for edge in self.edges]
        if len(edge_ids) != len(set(edge_ids)):
            seen = set()
            duplicates = [eid for eid in edge_ids if eid in seen or seen.add(eid)]
            raise ValueError(f"Duplicate edge ids: {duplicates}")

        for edge in self.edges:
            if edge.source not in node_ids or edge.target not in node_ids:
                raise ValueError(f"Edge {edge.id} references missing node: source={edge.source}, target={edge.target}")

        allowed_nodes = HSS_NODE_TYPES if self.paradigm == Paradigm.HSS else STEM_NODE_TYPES
        forbidden_nodes = [node.type for node in self.nodes if node.type not in {t.value for t in allowed_nodes}]
        if forbidden_nodes:
            raise ValueError(f"Forbidden node types: {forbidden_nodes}")

        allowed_edges = HSS_EDGE_TYPES if self.paradigm == Paradigm.HSS else STEM_EDGE_TYPES
        forbidden_edges = [edge.type for edge in self.edges if edge.type not in allowed_edges]
        if forbidden_edges:
            raise ValueError(f"Forbidden edge types: {forbidden_edges}")

        return self
