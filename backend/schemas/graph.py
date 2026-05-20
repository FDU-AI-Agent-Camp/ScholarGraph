"""Unified paper graph schemas (G6-ready)."""

from typing import Any

from pydantic import BaseModel, Field

from backend.schemas.paradigm import Paradigm


class GraphNode(BaseModel):
    id: str
    label: str
    type: str
    data: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    label: str
    type: str
    data: dict[str, Any] = Field(default_factory=dict)


class UnifiedPaperGraph(BaseModel):
    paper_id: str
    paradigm: Paradigm
    nodes: list[GraphNode]
    edges: list[GraphEdge]
