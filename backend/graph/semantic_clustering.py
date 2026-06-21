"""Second-order graph dehydration: semantic clustering and island stitching."""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from collections.abc import Sequence
from typing import Any

import re

from backend.config import Settings
from backend.graph.merge_graphs import _UnionFind
from backend.llm.embeddings import EmbeddingClient
from backend.schemas.extract_phase import ExtractedEdge, ExtractedGraph, ExtractedNode

logger = logging.getLogger(__name__)

# Extract the numeric prefix from ids like "e5_supports".
_EDGE_ID_INDEX_RE = re.compile(r"^e(\d+)_.*$")


def _next_edge_index(edges: list[ExtractedEdge]) -> int:
    """Return the next sequential integer for a generated edge id.

    Falls back to ``len(edges) + 1`` when existing ids do not follow the
    ``e{N}_{type}`` convention, so KNN bridges never reuse a numeric prefix.
    """
    max_idx = 0
    for edge in edges:
        match = _EDGE_ID_INDEX_RE.match(edge.id)
        if match:
            max_idx = max(max_idx, int(match.group(1)))
    if max_idx:
        return max_idx + 1
    return len(edges) + 1


# Edge type used for weak semantic bridges between isolated components.
_SEMANTIC_BRIDGE_TYPE = "RELATES_TO"
_SEMANTIC_BRIDGE_LABEL = "semantic_related"


def _node_text(node: ExtractedNode) -> str:
    """High-signal textual representation of a node for embedding.

    bge-m3's vector space is dense; long source spans dilute the core concept.
    We force the model to attend to the node type and label, and keep the
    supplementary evidence to a short 100-character snippet.
    """
    evidence = (node.source_span or "")[:100]
    text = f"[类型: {node.type}] 核心标签: {node.label}"
    if evidence:
        text += f" | 补充说明: {evidence}"
    return text


# Child node types that may be merged into their semantic parent types.
# The key is the *absorbed* (subordinate) type; the value is the set of parent
# types it is allowed to collapse into. All other cross-type pairs are blocked.
# Keep this list conservative: central concept types (Claim/Method/Thesis) must
# not absorb each other, otherwise broad topic terms become "super black holes".
_CROSS_TYPE_MERGE_RULES: dict[str, set[str]] = {
    "SubArgument": {"Claim"},
    "Evidence": set(),  # Evidence is already folded; if it survives, keep it real.
    "ObjectOrData": set(),  # Data objects must stay distinct from concepts.
    "Dataset": {"Method"},
    "Metric": {"Method"},
    "Baseline": {"Method"},
    "ResearchQuestion": {"Thesis"},
    "AnalyticalLens": set(),
    "IntellectualContext": set(),
    "Claim": set(),
    "Method": set(),
    "Thesis": set(),
}

# When two different node types are allowed to merge, apply a similarity penalty
# so the cross-type threshold is effectively higher (e.g. 0.85 -> 0.90).
_CROSS_TYPE_PENALTY = 0.05


def _cross_type_merge_allowed(type_a: str, type_b: str) -> bool:
    """Return True if two different node types are allowed to merge."""
    if type_a == type_b:
        return True
    allowed_for_a = _CROSS_TYPE_MERGE_RULES.get(type_a, set())
    allowed_for_b = _CROSS_TYPE_MERGE_RULES.get(type_b, set())
    return type_b in allowed_for_a or type_a in allowed_for_b


# Root-election priority: lower number = preferred as the canonical root when a
# cluster contains multiple node types. This prevents a child type (e.g.
# SubArgument) from becoming the root and swallowing its parent type (Claim).
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


def _cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity between two equal-length vectors."""
    if not a or not b:
        return 0.0
    dot = math.fsum(x * y for x, y in zip(a, b))
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


def _elect_root(cluster_ids: set[str], degrees: dict[str, int], nodes_by_id: dict[str, ExtractedNode]) -> str:
    """Elect the canonical root for a semantic cluster.

    Prefer more general node types over subordinate types, then highest degree,
    then confidence, then deterministic id.
    """

    def _score(node_id: str) -> tuple[int, int, float, str]:
        node = nodes_by_id[node_id]
        priority = _ROOT_TYPE_PRIORITY.get(node.type, _DEFAULT_ROOT_PRIORITY)
        return (priority, -degrees.get(node_id, 0), -node.confidence, node_id)

    return min(cluster_ids, key=_score)


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


def _merge_clusters(
    nodes: list[ExtractedNode],
    edges: list[ExtractedEdge],
    clusters: list[set[str]],
) -> tuple[list[ExtractedNode], list[ExtractedEdge], dict[str, str], int]:
    """Merge each semantic cluster into a single elected root node."""
    nodes_by_id = {node.id: node for node in nodes}
    degrees = _compute_degrees(nodes, edges)

    id_map: dict[str, str] = {}
    cluster_roots: dict[str, str] = {}
    for cluster in clusters:
        if len(cluster) <= 1:
            root = next(iter(cluster))
            id_map[root] = root
            cluster_roots[root] = root
        else:
            root = _elect_root(cluster, degrees, nodes_by_id)
            cluster_roots[root] = root
            for node_id in cluster:
                id_map[node_id] = root

    # Initialize each canonical root from its own node object, ensuring the
    # returned node id matches the canonical root id even if an alias appeared
    # first in the original node list.
    new_nodes_by_id: dict[str, ExtractedNode] = {}
    for root_id in cluster_roots.values():
        root_node = nodes_by_id[root_id]
        new_nodes_by_id[root_id] = root_node.model_copy(update={"id": root_id})

    for node in nodes:
        root_id = id_map[node.id]
        if node.id == root_id:
            continue

        existing = new_nodes_by_id[root_id]
        new_data = dict(existing.data)

        aliases = new_data.get("semantic_aliases", [])
        if not isinstance(aliases, list):
            aliases = []
        aliases.append({
            "id": node.id,
            "label": node.label,
            "type": node.type,
            "source_span": node.source_span,
        })
        new_data["semantic_aliases"] = aliases

        # Merge folded leaves if the alias carried them.
        folded = node.data.get("folded_leaves")
        if isinstance(folded, list):
            existing_folded = new_data.get("folded_leaves", [])
            if not isinstance(existing_folded, list):
                existing_folded = []
            existing_folded.extend(folded)
            new_data["folded_leaves"] = existing_folded

        # Keep the longest source_span as evidence.
        best_span = node.source_span
        if existing.source_span and best_span:
            best_span = max(existing.source_span, best_span, key=len)
        elif existing.source_span:
            best_span = existing.source_span

        new_nodes_by_id[root_id] = existing.model_copy(
            update={
                "source_span": best_span,
                "data": new_data,
                "confidence": max(existing.confidence, node.confidence),
            }
        )

    # Remap edges through the cluster map and deduplicate.
    # Use the original id as a placeholder; ids are reassigned sequentially
    # after deduplication so that downstream KNN bridging cannot collide with
    # gaps left by dropped self-loops or duplicate edges.
    def _richer_edge(a: ExtractedEdge, b: ExtractedEdge) -> ExtractedEdge:
        """Keep the edge that carries more semantic information.

        Prefer longer rationale, then longer source_span. This avoids data
        bloat from string concatenation while preserving the richest logic
        path after node merges.
        """
        a_rationale_len = len(a.rationale or "")
        b_rationale_len = len(b.rationale or "")
        if b_rationale_len > a_rationale_len:
            return b
        if a_rationale_len > b_rationale_len:
            return a
        # Tie-break on source_span length when rationale is equal or absent.
        if b.source_span and len(b.source_span) > len(a.source_span or ""):
            return b
        return a

    dedup: dict[tuple[str, str, str, str], ExtractedEdge] = {}
    for edge in edges:
        source = id_map.get(edge.source, edge.source)
        target = id_map.get(edge.target, edge.target)
        if source == target:
            continue
        key = (source, target, edge.type, edge.label)
        remapped = edge.model_copy(update={"source": source, "target": target})
        existing = dedup.get(key)
        if existing is None:
            dedup[key] = remapped
        else:
            dedup[key] = _richer_edge(existing, remapped)

    merged_edges: list[ExtractedEdge] = []
    for idx, edge in enumerate(dedup.values(), start=1):
        merged_edges.append(edge.model_copy(update={"id": f"e{idx}_{edge.type.lower()}"}))

    merged_count = sum(1 for cluster in clusters if len(cluster) > 1)
    return list(new_nodes_by_id.values()), merged_edges, id_map, merged_count


def _add_knn_bridges(
    nodes: list[ExtractedNode],
    edges: list[ExtractedEdge],
    embeddings: list[list[float]],
    knn_threshold: float,
) -> tuple[list[ExtractedEdge], int]:
    """Pull small isolated components into the main component via weak semantic edges."""
    nodes_by_id = {node.id: node for node in nodes}
    components = _build_components(nodes, edges)
    if len(components) <= 1:
        return edges, 0

    components.sort(key=len, reverse=True)
    main_component = components[0]
    main_ids = list(main_component)
    main_indices = [i for i, node in enumerate(nodes) if node.id in main_component]

    existing_pairs: set[tuple[str, str]] = set()
    for edge in edges:
        existing_pairs.add((edge.source, edge.target))
        existing_pairs.add((edge.target, edge.source))

    new_edges = list(edges)
    bridges_added = 0
    next_edge_id = _next_edge_index(new_edges)

    for component in components[1:]:
        # Representative: highest-degree node inside the island.
        component_degrees = _compute_degrees(
            [nodes_by_id[node_id] for node_id in component],
            [edge for edge in edges if edge.source in component or edge.target in component],
        )
        representative_id = max(component, key=lambda node_id: (component_degrees.get(node_id, 0), node_id))
        rep_index = next(i for i, node in enumerate(nodes) if node.id == representative_id)
        rep_vector = embeddings[rep_index]

        best_similarity = -1.0
        best_main_id: str | None = None
        for main_index in main_indices:
            similarity = _cosine_similarity(rep_vector, embeddings[main_index])
            if similarity > best_similarity:
                best_similarity = similarity
                best_main_id = nodes[main_index].id

        if best_main_id is None or best_similarity < knn_threshold:
            continue

        pair = (representative_id, best_main_id)
        if pair in existing_pairs:
            continue

        new_edges.append(
            ExtractedEdge(
                id=f"e{next_edge_id}_{_SEMANTIC_BRIDGE_TYPE.lower()}",
                source=representative_id,
                target=best_main_id,
                label=_SEMANTIC_BRIDGE_LABEL,
                type=_SEMANTIC_BRIDGE_TYPE,
                source_span=None,
                data={"semantic_similarity": round(best_similarity, 4)},
            )
        )
        existing_pairs.add(pair)
        existing_pairs.add((best_main_id, representative_id))
        bridges_added += 1
        next_edge_id += 1

    return new_edges, bridges_added


def _deduplicate_edges_by_type(edges: list[ExtractedEdge]) -> list[ExtractedEdge]:
    """Collapse parallel edges that share source, target and edge type.

    After node merges, edges originally pointing to distinct aliases may be
    redirected to the same canonical root, producing parallel edges. AntV G6
    renders these as thick overlapping lines, so we keep only the first edge
    for each (source, target, type) triple.
    """
    seen: set[tuple[str, str, str]] = set()
    unique_edges: list[ExtractedEdge] = []
    for edge in edges:
        key = (edge.source, edge.target, edge.type)
        if key in seen:
            continue
        seen.add(key)
        unique_edges.append(edge)
    return unique_edges


async def semantic_cluster_and_merge(
    graph: ExtractedGraph,
    settings: Settings,
    *,
    embedding_client: EmbeddingClient | None = None,
) -> ExtractedGraph:
    """Resolve synonym nodes via embedding similarity and stitch isolated islands.

    The pipeline:

    1. Embed each node's label (+ source span + folded leaves).
    2. Cluster nodes whose cosine similarity >= ``semantic_similarity_threshold``.
    3. Merge each cluster into its highest-degree root, remapping edges.
    4. For remaining small components, add a weak ``RELATES_TO`` bridge to the
       nearest node in the largest component if similarity >= ``semantic_knn_threshold``.
    """
    if not settings.semantic_clustering_enabled or len(graph.nodes) < 2:
        return graph

    client = embedding_client or EmbeddingClient(settings)

    texts = [_node_text(node) for node in graph.nodes]
    try:
        embeddings = await client.embed_texts(texts)
    except Exception as exc:
        logger.warning("semantic_clustering_embedding_failed", extra={"error": str(exc)})
        warnings = list(graph.warnings)
        warnings.append(f"SEMANTIC_CLUSTERING_SKIPPED:{type(exc).__name__}")
        return graph.model_copy(update={"warnings": warnings})

    if len(embeddings) != len(graph.nodes):
        raise ValueError(
            f"Embedding count mismatch: {len(embeddings)} vectors for {len(graph.nodes)} nodes"
        )

    # 1. Pairwise similarity clustering with a dynamic type firewall.
    node_ids = [node.id for node in graph.nodes]
    node_types = [node.type for node in graph.nodes]
    uf = _UnionFind()
    for i in range(len(node_ids)):
        uf.find(node_ids[i])
    for i in range(len(node_ids)):
        for j in range(i + 1, len(node_ids)):
            similarity = _cosine_similarity(embeddings[i], embeddings[j])
            if node_types[i] != node_types[j]:
                if _cross_type_merge_allowed(node_types[i], node_types[j]):
                    # Raise the bar for cross-type merges to avoid loose hubs.
                    similarity = max(0.0, similarity - _CROSS_TYPE_PENALTY)
                else:
                    # Hard firewall for forbidden cross-type pairs.
                    similarity = 0.0
            if similarity >= settings.semantic_similarity_threshold_effective:
                uf.union(node_ids[i], node_ids[j])

    clusters: dict[str, set[str]] = defaultdict(set)
    for node_id in node_ids:
        clusters[uf.find(node_id)].add(node_id)
    cluster_list = list(clusters.values())

    nodes_after_merge, edges_after_merge, id_map, merged_clusters = _merge_clusters(
        graph.nodes, graph.edges, cluster_list
    )

    # Build embeddings aligned with the merged node list: each kept node uses the
    # embedding of its cluster root.
    root_to_embedding: dict[str, list[float]] = {}
    for node_id, emb in zip(node_ids, embeddings):
        root_id = id_map[node_id]
        if root_id not in root_to_embedding:
            root_to_embedding[root_id] = emb
    merged_embeddings = [root_to_embedding[node.id] for node in nodes_after_merge]

    # 2. K-NN island bridging.
    final_edges, bridges_added = _add_knn_bridges(
        nodes_after_merge,
        edges_after_merge,
        merged_embeddings,
        settings.semantic_knn_threshold_effective,
    )

    # 3. Collapse parallel edges produced by node merges / K-NN bridging.
    final_edges = _deduplicate_edges_by_type(final_edges)

    warnings = list(graph.warnings)
    if merged_clusters:
        warnings.append(f"SEMANTIC_CLUSTERS_MERGED:{merged_clusters}")
    if bridges_added:
        warnings.append(f"SEMANTIC_KNN_EDGES_ADDED:{bridges_added}")

    return graph.model_copy(update={"nodes": nodes_after_merge, "edges": final_edges, "warnings": warnings})
