# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Text helpers and low-level utilities for semantic clustering."""

from __future__ import annotations

import logging
import math
import re
from collections import defaultdict
from collections.abc import Sequence

import numpy as np

from backend.schemas.extract_phase import ExtractedEdge, ExtractedNode

logger = logging.getLogger(__name__)

_EDGE_ID_INDEX_RE = re.compile(r"^e(\d+)_.*$")

_SEMANTIC_BRIDGE_TYPE = "SEMANTICALLY_RELATED_TO"
_SEMANTIC_BRIDGE_LABEL = "semantically_related"

_ROOT_TYPE_PRIORITY: dict[str, int] = {
    "Thesis": 0,
    "ResearchQuestion": 0,
    "Method": 1,
    "Claim": 2,
    "Experiment": 3,
    "SubArgument": 4,
    "AnalyticalLens": 5,
    "IntellectualContext": 6,
    "Finding": 7,
    "Dataset": 8,
    "Metric": 9,
    "Baseline": 10,
    "Evidence": 11,
    "ObjectOrData": 12,
}
_DEFAULT_ROOT_PRIORITY = 99


def _next_edge_index(edges: list[ExtractedEdge]) -> int:
    """Return the next sequential integer for a generated edge id."""
    max_idx = 0
    for edge in edges:
        match = _EDGE_ID_INDEX_RE.match(edge.id)
        if match:
            max_idx = max(max_idx, int(match.group(1)))
    if max_idx:
        return max_idx + 1
    return len(edges) + 1


def _node_text(node: ExtractedNode) -> str:
    """High-signal textual representation of a node for embedding."""
    label = node.label.strip()
    sub_type = node.sub_type or node.data.get("sub_type") or "General"
    description = node.description or node.data.get("description") or ""

    text = f"类型: {node.type} | 细分类别: {sub_type} | 核心概念: {label}"
    if description:
        text += f" | 语义定义: {description}"
    return text


def _cross_type_merge_allowed(type_a: str, type_b: str) -> bool:
    """Return True only when two nodes share the exact same type."""
    return type_a == type_b


def _group_nodes_by_type(nodes: list[ExtractedNode]) -> dict[str, list[tuple[int, ExtractedNode]]]:
    """Group nodes by their type, preserving original indices."""
    groups: dict[str, list[tuple[int, ExtractedNode]]] = defaultdict(list)
    for idx, node in enumerate(nodes):
        groups[node.type].append((idx, node))
    return groups


def _coarse_filter_pairs(
    nodes: list[ExtractedNode],
    embeddings: np.ndarray,
    threshold: float,
) -> list[tuple[str, str, float]]:
    """Return high-risk merge candidate pairs using batched matrix math."""
    n = len(nodes)
    if n < 2 or embeddings.shape[0] != n:
        return []

    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    safe_norms = np.where(norms == 0, 1.0, norms)
    normalized = embeddings / safe_norms

    similarity_matrix = np.dot(normalized, normalized.T)
    rows, cols = np.triu_indices(n, k=1)
    scores = similarity_matrix[rows, cols]
    mask = scores > threshold

    pairs: list[tuple[str, str, float]] = []
    for i, j, score in zip(rows[mask], cols[mask], scores[mask], strict=True):
        pairs.append((nodes[i].id, nodes[j].id, float(score)))
    return pairs


def _cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity between two equal-length vectors."""
    if not a or not b:
        return 0.0
    dot = math.fsum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(math.fsum(x * x for x in a))
    norm_b = math.sqrt(math.fsum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _compute_degrees(nodes: list[ExtractedNode], edges: list[ExtractedEdge]) -> dict[str, int]:
    """Return total degree (in + out) for each node id."""
    node_ids = {node.id for node in nodes}
    degrees: dict[str, int] = {node.id: 0 for node in nodes}
    for edge in edges:
        if edge.source in node_ids:
            degrees[edge.source] = degrees.get(edge.source, 0) + 1
        if edge.target in node_ids:
            degrees[edge.target] = degrees.get(edge.target, 0) + 1
    return degrees


def _fuse_descriptions(descriptions: list[str]) -> str:
    """Merge multiple node descriptions into a single canonical description."""
    unique: list[str] = []
    seen: set[str] = set()
    for desc in descriptions:
        desc = desc.strip()
        if desc and desc not in seen:
            seen.add(desc)
            unique.append(desc)
    if not unique:
        return ""
    if len(unique) == 1:
        return unique[0]
    return " | ".join(unique)


def _build_components(nodes: list[ExtractedNode], edges: list[ExtractedEdge]) -> list[set[str]]:
    """Return connected components as sets of node ids (undirected)."""
    node_ids = {node.id for node in nodes}
    adj: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    for edge in edges:
        if edge.source in node_ids and edge.target in node_ids:
            adj[edge.source].add(edge.target)
            adj[edge.target].add(edge.source)

    visited: set[str] = set()
    components: list[set[str]] = []
    for node_id in node_ids:
        if node_id in visited:
            continue
        stack = [node_id]
        visited.add(node_id)
        component: set[str] = set()
        while stack:
            current = stack.pop()
            component.add(current)
            for neighbour in adj[current]:
                if neighbour not in visited:
                    visited.add(neighbour)
                    stack.append(neighbour)
        components.append(component)
    return components


def _deduplicate_edges_by_type(edges: list[ExtractedEdge]) -> list[ExtractedEdge]:
    """Collapse parallel edges that share source, target and edge type."""
    seen: set[tuple[str, str, str]] = set()
    unique_edges: list[ExtractedEdge] = []
    for edge in edges:
        key = (edge.source, edge.target, edge.type)
        if key in seen:
            continue
        seen.add(key)
        unique_edges.append(edge)
    return unique_edges
