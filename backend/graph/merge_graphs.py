"""Merge per-chunk extraction results into a single global graph."""

from __future__ import annotations

import logging
import re
from typing import Any

from backend.schemas.extract_phase import (
    ExtractedEdge,
    ExtractedEdgeList,
    ExtractedGraph,
    ExtractedNode,
    ExtractedNodeList,
)
from backend.schemas.paradigm import Paradigm

logger = logging.getLogger(__name__)

# Node types that are safe to fold into their single neighbour during heuristic
# baseline pruning. These are typically secondary evidentiary nodes that merely
# decorate a Claim/Thesis/Method rather than acting as graph navigation hubs.
_FOLDABLE_LEAF_TYPES = frozenset(
    {
        "Evidence",
        "ObjectOrData",
        "Dataset",
        "Metric",
        "Baseline",
    }
)

# Unicode replacement character produced by broken PDF font mapping.
_REPLACEMENT_CHAR = "\ufffd"
_GARBLED_RUN_RE = re.compile(r"\ufffd{3,}")


def _is_garbled(text: str | None) -> bool:
    """Detect labels corrupted by PDF font-mapping failures.

    A label is considered garbled when:
    - it contains 3+ consecutive U+FFFD replacement characters, or
    - more than 50% of its characters are U+FFFD.
    """
    if not text:
        return False
    if _GARBLED_RUN_RE.search(text):
        return True
    replacement_count = text.count(_REPLACEMENT_CHAR)
    return replacement_count / len(text) > 0.5


def _sanitize_graph_labels(graph: ExtractedGraph) -> ExtractedGraph:
    """Replace garbled node labels with type-safe fallbacks.

    Nodes are never deleted, preserving graph connectivity. The original label is
    preserved in ``node.data["original_label"]`` for debugging.
    """
    new_nodes: list[ExtractedNode] = []
    sanitized_count = 0

    for node in graph.nodes:
        if not _is_garbled(node.label):
            new_nodes.append(node)
            continue

        fallback = f"[{node.type}]" if node.type else "[Corrupted Node Data]"
        new_data = dict(node.data)
        new_data["original_label"] = node.label
        new_data["label_sanitized"] = True
        new_nodes.append(node.model_copy(update={"label": fallback, "data": new_data}))
        sanitized_count += 1

    if sanitized_count == 0:
        return graph

    warnings = list(graph.warnings)
    warnings.append(f"GARBLED_LABELS_SANITIZED:{sanitized_count}")
    return graph.model_copy(update={"nodes": new_nodes, "warnings": warnings})


class _UnionFind:
    """Disjoint-set union-find with path compression."""

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        """Return the canonical representative of ``x``."""
        if x not in self._parent:
            self._parent[x] = x
            return x
        # Path compression.
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[x] != root:
            parent = self._parent[x]
            self._parent[x] = root
            x = parent
        return root

    def union(self, x: str, y: str) -> None:
        """Merge the sets containing ``x`` and ``y``."""
        rx, ry = self.find(x), self.find(y)
        if rx != ry:
            self._parent[ry] = rx


def _normalize_label(label: str) -> str:
    """Normalize a node label for duplicate detection."""
    lowered = label.lower().strip()
    # Remove common punctuation and collapse whitespace.
    cleaned = re.sub(r"[^\w\s]", "", lowered)
    return re.sub(r"\s+", " ", cleaned).strip()


def _merge_node_data(nodes: list[ExtractedNode]) -> dict[str, Any]:
    """Merge ``data`` dicts from alias nodes, preserving alias ids."""
    merged: dict[str, Any] = {}
    aliases = [n.id for n in nodes]
    if aliases:
        merged["merged_aliases"] = aliases
    for node in nodes:
        for key, value in node.data.items():
            if key not in merged:
                merged[key] = value
    return merged


def merge_node_lists(
    node_lists: list[ExtractedNodeList],
    *,
    prefixed: bool = False,
) -> tuple[ExtractedNodeList, dict[str, str]]:
    """Combine multiple per-chunk node lists and merge obvious duplicates.

    Args:
        node_lists: One node list per chunk.
        prefixed: When ``True``, node ids are already chunk-scoped (e.g.
            ``c0_n1``) and will not be prefixed again. Use this when the caller
            has already scoped ids before edge extraction.

    Duplicate detection is currently based on normalized ``(label, type)``.
    Identical entries are merged via union-find; the first occurrence becomes
    the canonical node. A future upgrade can replace this with embedding-based
    clustering.

    Returns:
        A tuple of ``(merged_node_list, id_map)`` where ``id_map`` maps every
        original chunk-scoped node id to its canonical global id.

    Raises:
        ValueError: When ``node_lists`` is empty.
    """
    if not node_lists:
        raise ValueError("Cannot merge empty node lists.")

    paradigm = node_lists[0].paradigm

    # Step 1: Give every node a chunk-scoped id to avoid collisions.
    renamed: dict[str, ExtractedNode] = {}
    for chunk_idx, node_list in enumerate(node_lists):
        for node in node_list.nodes:
            new_id = node.id if prefixed else f"c{chunk_idx}_{node.id}"
            renamed[new_id] = node.model_copy(update={"id": new_id})

    # Step 2: Union duplicates by normalized (label, type).
    uf = _UnionFind()
    key_to_canonical: dict[tuple[str, str], str] = {}
    for node_id, node in renamed.items():
        key = (_normalize_label(node.label), node.type)
        if key in key_to_canonical:
            uf.union(key_to_canonical[key], node_id)
        else:
            key_to_canonical[key] = node_id

    # Step 3: Build id map and canonical nodes.
    id_map = {node_id: uf.find(node_id) for node_id in renamed}

    groups: dict[str, list[ExtractedNode]] = {}
    for node_id, node in renamed.items():
        root = id_map[node_id]
        groups.setdefault(root, []).append(node)

    merged_nodes: list[ExtractedNode] = []
    for root_id, alias_nodes in groups.items():
        # Representative: the node whose id is the root (first occurrence).
        representative = next(n for n in alias_nodes if n.id == root_id)
        # Keep the longest source_span as the most informative evidence.
        spans = [n.source_span for n in alias_nodes if n.source_span]
        best_span = max(spans, key=len) if spans else None
        # Highest confidence among aliases.
        best_confidence = max((n.confidence for n in alias_nodes), default=1.0)
        merged_data = _merge_node_data(alias_nodes)
        merged_nodes.append(
            representative.model_copy(
                update={
                    "source_span": best_span,
                    "confidence": best_confidence,
                    "data": merged_data,
                }
            )
        )

    # Preserve original order as much as possible (first occurrence order).
    merged_nodes.sort(key=lambda n: n.data.get("merged_aliases", [n.id])[0])

    warnings = list(dict.fromkeys(w for node_list in node_lists for w in node_list.warnings))

    return ExtractedNodeList(paradigm=paradigm, nodes=merged_nodes, warnings=warnings), id_map


def merge_edge_lists(
    edge_lists: list[ExtractedEdgeList],
    id_map: dict[str, str],
) -> ExtractedEdgeList:
    """Combine per-chunk edge lists, remap source/target ids, and deduplicate.

    Edge deduplication key is ``(source, target, type, label)`` after id
    remapping. Edge ids are regenerated to ensure global uniqueness.
    """
    if not edge_lists:
        return ExtractedEdgeList(paradigm=Paradigm.HSS, edges=[], node_ids=[])

    paradigm = edge_lists[0].paradigm

    seen: dict[tuple[str, str, str, str], ExtractedEdge] = {}
    for edge_list in edge_lists:
        for edge in edge_list.edges:
            raw_source = edge.source.lstrip("#")
            raw_target = edge.target.lstrip("#")
            source = id_map.get(raw_source, raw_source)
            target = id_map.get(raw_target, raw_target)
            key = (source, target, edge.type, edge.label)
            existing = seen.get(key)
            if existing is None:
                seen[key] = edge.model_copy(update={"source": source, "target": target})
            elif edge.source_span and len(edge.source_span) > len(existing.source_span or ""):
                seen[key] = edge.model_copy(update={"source": source, "target": target})

    merged_edges: list[ExtractedEdge] = []
    for idx, edge in enumerate(seen.values(), start=1):
        merged_edges.append(edge.model_copy(update={"id": f"e{idx}_{edge.type.lower()}"}))

    warnings = list(dict.fromkeys(w for edge_list in edge_lists for w in edge_list.warnings))

    return ExtractedEdgeList(
        paradigm=paradigm,
        edges=merged_edges,
        node_ids=[],
        warnings=warnings,
    )


def _heuristic_prune(graph: ExtractedGraph) -> ExtractedGraph:
    """First-order graph dehydration: zero-degree purge + leaf-node folding.

    This is intentionally cheap and deterministic. It runs in a single pass and
    is designed to shrink the graph by 30-40% before any embedding-based or
    community-detection pruning happens.
    """
    nodes = graph.nodes
    edges = graph.edges

    node_by_id = {node.id: node for node in nodes}
    incident_edges: dict[str, list[ExtractedEdge]] = {node.id: [] for node in nodes}

    for edge in edges:
        if edge.source in incident_edges:
            incident_edges[edge.source].append(edge)
        if edge.target in incident_edges:
            incident_edges[edge.target].append(edge)

    # 1. Zero-Degree Purge: remove nodes with no incident edges.
    zero_degree_ids = {node.id for node in nodes if not incident_edges[node.id]}
    kept_node_ids = set(node_by_id.keys()) - zero_degree_ids

    # 2. Leaf-Node Folding: collapse degree-1 secondary nodes into their parent.
    folded_leaf_ids: set[str] = set()
    parent_folds: dict[str, list[dict[str, Any]]] = {}

    for leaf_id in sorted(kept_node_ids):
        if leaf_id in folded_leaf_ids:
            continue
        leaf = node_by_id[leaf_id]
        if leaf.type not in _FOLDABLE_LEAF_TYPES:
            continue

        leaf_edges = incident_edges[leaf_id]
        if len(leaf_edges) != 1:
            continue

        edge = leaf_edges[0]
        parent_id = edge.target if edge.source == leaf_id else edge.source
        if parent_id not in kept_node_ids or parent_id in folded_leaf_ids:
            continue

        parent = node_by_id[parent_id]
        # Avoid ambiguous folding when two foldable leaves point at each other.
        if parent.type in _FOLDABLE_LEAF_TYPES and len(incident_edges[parent_id]) == 1:
            continue

        parent_folds.setdefault(parent_id, []).append(
            {
                "leaf_id": leaf_id,
                "leaf_type": leaf.type,
                "label": leaf.label,
                "source_span": leaf.source_span,
            }
        )
        folded_leaf_ids.add(leaf_id)

    removed_ids = zero_degree_ids | folded_leaf_ids
    new_nodes: list[ExtractedNode] = []
    for node in nodes:
        if node.id in removed_ids:
            continue
        folds = parent_folds.get(node.id)
        if folds:
            new_data = dict(node.data)
            existing = new_data.setdefault("folded_leaves", [])
            if isinstance(existing, list):
                existing.extend(folds)
            else:
                new_data["folded_leaves"] = folds
            node = node.model_copy(update={"data": new_data})
        new_nodes.append(node)

    new_edges = [edge for edge in edges if edge.source not in removed_ids and edge.target not in removed_ids]

    warnings = list(graph.warnings)
    if zero_degree_ids:
        warnings.append(f"PRUNED_ZERO_DEGREE:{len(zero_degree_ids)}")
    if folded_leaf_ids:
        warnings.append(f"FOLDED_LEAVES:{len(folded_leaf_ids)}")

    return graph.model_copy(update={"nodes": new_nodes, "edges": new_edges, "warnings": warnings})


def merge_graphs(
    paper_id: str,
    title: str | None,
    paradigm: Paradigm,
    node_lists: list[ExtractedNodeList],
    edge_lists: list[ExtractedEdgeList],
    summary: str | None = None,
    node_ids_prefixed: bool = False,
    extra_warnings: list[str] | None = None,
    prune: bool = False,
) -> ExtractedGraph:
    """Merge multiple per-chunk extraction results into a single validated graph.

    Args:
        prune: When ``True``, apply heuristic baseline pruning (zero-degree
            purge + leaf-node folding) before returning. Disabled by default so
            low-level merge semantics remain stable for callers that need the
            raw graph; the chunked extraction pipeline enables it explicitly.
    """
    merged_nodes, id_map = merge_node_lists(node_lists, prefixed=node_ids_prefixed)
    merged_edges = merge_edge_lists(edge_lists, id_map)

    node_ids = {node.id for node in merged_nodes.nodes}
    valid_edges = [edge for edge in merged_edges.edges if edge.source in node_ids and edge.target in node_ids]
    removed = len(merged_edges.edges) - len(valid_edges)
    dangling_warning = f"DANGLING_EDGES_REMOVED:{removed}" if removed else ""

    warnings = list(dict.fromkeys(merged_nodes.warnings + merged_edges.warnings + (extra_warnings or [])))
    if dangling_warning:
        warnings.append(dangling_warning)

    graph = ExtractedGraph(
        paper_id=paper_id,
        title=title,
        paradigm=paradigm,
        nodes=merged_nodes.nodes,
        edges=valid_edges,
        summary=summary,
        warnings=warnings,
    )

    if prune:
        graph = _heuristic_prune(graph)

    return _sanitize_graph_labels(graph)
