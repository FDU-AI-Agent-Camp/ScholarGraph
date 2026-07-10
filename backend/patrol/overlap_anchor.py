"""Internal anchor dataclass used by method_overlap patrol logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from backend.schemas.graph import GraphNode
from backend.schemas.patrol import OverlapType


def _normalize_label(label: str) -> str:
    """Normalize a node label for overlap comparison."""
    return label.strip().lower()


@dataclass(frozen=True)
class _OverlapAnchor:
    """Physical anchor for an overlap relationship between two papers.

    This is the source of truth for structured_points and node_refs: every
    anchor returned by the local state machine must be reflected in the final
    output.  The LLM injects semantic flesh (usage / evidence) on top of this
    skeleton.
    """

    left_node: GraphNode
    right_node: GraphNode
    overlap_kind: OverlapType
    match_type: Literal["literal", "semantic"]
    overlap_score: float

    @property
    def pair_label(self) -> str:
        return f"{self.left_node.label} <-> {self.right_node.label}"

    @property
    def overlap_label(self) -> str:
        """Short representative label for the overlapping item."""
        if _normalize_label(self.left_node.label) == _normalize_label(self.right_node.label):
            return self.left_node.label
        # Prefer the shorter label as the canonical representative for semantic pairs.
        left = self.left_node.label
        right = self.right_node.label
        return left if len(left) <= len(right) else right
