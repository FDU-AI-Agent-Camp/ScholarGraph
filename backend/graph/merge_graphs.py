"""Merge per-chunk extraction results into a single global graph."""

from __future__ import annotations

import logging
import re
from typing import Any

from backend.schemas.extract_phase import ExtractedEdge, ExtractedEdgeList, ExtractedGraph, ExtractedNode, ExtractedNodeList
from backend.schemas.paradigm import Paradigm

logger = logging.getLogger(__name__)


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


def merge_graphs(
    paper_id: str,
    title: str | None,
    paradigm: Paradigm,
    node_lists: list[ExtractedNodeList],
    edge_lists: list[ExtractedEdgeList],
    summary: str | None = None,
    node_ids_prefixed: bool = False,
    extra_warnings: list[str] | None = None,
) -> ExtractedGraph:
    """Merge multiple per-chunk extraction results into a single validated graph."""
    merged_nodes, id_map = merge_node_lists(node_lists, prefixed=node_ids_prefixed)
    merged_edges = merge_edge_lists(edge_lists, id_map)

    node_ids = {node.id for node in merged_nodes.nodes}
    valid_edges = [edge for edge in merged_edges.edges if edge.source in node_ids and edge.target in node_ids]
    removed = len(merged_edges.edges) - len(valid_edges)
    dangling_warning = f"DANGLING_EDGES_REMOVED:{removed}" if removed else ""

    warnings = list(dict.fromkeys(merged_nodes.warnings + merged_edges.warnings + (extra_warnings or [])))
    if dangling_warning:
        warnings.append(dangling_warning)

    return ExtractedGraph(
        paper_id=paper_id,
        title=title,
        paradigm=paradigm,
        nodes=merged_nodes.nodes,
        edges=valid_edges,
        summary=summary,
        warnings=warnings,
    )
