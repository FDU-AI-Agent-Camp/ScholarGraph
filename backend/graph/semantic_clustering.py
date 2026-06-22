"""Second-order graph dehydration: semantic clustering and island stitching."""

from __future__ import annotations

import logging
import math
import re
from collections import defaultdict
from collections.abc import Sequence

import numpy as np

from backend.config import Settings
from backend.graph.merge_graphs import _UnionFind
from backend.llm.embeddings import EmbeddingClient
from backend.llm.reranker import RerankerClient
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
# This is intentionally distinct from the forbidden LLM fallback "RELATES_TO".
_SEMANTIC_BRIDGE_TYPE = "SEMANTICALLY_RELATED_TO"
_SEMANTIC_BRIDGE_LABEL = "semantically_related"


def _node_text(node: ExtractedNode) -> str:
    """High-signal textual representation of a node for embedding.

    Raw source_span is intentionally excluded from embedding input because it
    contains unstructured local context that dilutes the core concept and
    produces under-merging (e.g. the same dataset expressed in different chunks).
    Instead we use a structured template with optional subtype and definition.
    """
    label = node.label.strip()
    sub_type = node.sub_type or node.data.get("sub_type") or "General"
    description = node.description or node.data.get("description") or ""

    text = f"类型: {node.type} | 细分类别: {sub_type} | 核心概念: {label}"
    if description:
        text += f" | 语义定义: {description}"
    return text


def _cross_type_merge_allowed(type_a: str, type_b: str) -> bool:
    """Return True only when two nodes share the exact same type.

    Stage-1 hard type firewall: cross-type comparisons are forbidden entirely.
    This eliminates spurious overlaps in vector space (e.g. a ``Method`` named
    after a ``Dataset``) and minimizes wasted embedding/reranker work.
    """
    return type_a == type_b


def _group_nodes_by_type(nodes: list[ExtractedNode]) -> dict[str, list[tuple[int, ExtractedNode]]]:
    """Group nodes by their type, preserving original indices.

    Returns a mapping ``type -> [(original_index, node), ...]``.  Grouping by
    type is the prerequisite for the stage-2 matrix coarse-filter: it keeps the
    similarity matrix small and guarantees the hard type firewall.
    """
    groups: dict[str, list[tuple[int, ExtractedNode]]] = defaultdict(list)
    for idx, node in enumerate(nodes):
        groups[node.type].append((idx, node))
    return groups


def _coarse_filter_pairs(
    nodes: list[ExtractedNode],
    embeddings: np.ndarray,
    threshold: float,
) -> list[tuple[str, str, float]]:
    """Return high-risk merge candidate pairs using batched matrix math.

    ``embeddings`` must have shape ``(N, D)`` where ``N == len(nodes)``.  The
    matrix is L2-normalized row-wise so that ``dot(E, E.T)`` equals cosine
    similarity.  Only the upper triangle (``i < j``) is considered, avoiding
    self-pairs and duplicates.
    """
    n = len(nodes)
    if n < 2 or embeddings.shape[0] != n:
        return []

    # L2 normalize per row.  Zero vectors are left as zeros to avoid division
    # by zero and to produce zero similarity with everything else.
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    safe_norms = np.where(norms == 0, 1.0, norms)
    normalized = embeddings / safe_norms

    similarity_matrix = np.dot(normalized, normalized.T)

    # Upper triangle without the diagonal: i < j.
    rows, cols = np.triu_indices(n, k=1)
    scores = similarity_matrix[rows, cols]
    mask = scores > threshold

    pairs: list[tuple[str, str, float]] = []
    for i, j, score in zip(rows[mask], cols[mask], scores[mask], strict=True):
        pairs.append((nodes[i].id, nodes[j].id, float(score)))
    return pairs


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
    """Merge each semantic cluster into a single elected root node.

    After merging, parallel edges redirected to the same canonical root are
    deduplicated. The surviving edge keeps the richest semantic payload:
    longer rationale wins, with source_span length used as a tie-breaker.
    Final edge ids are reassigned sequentially so that downstream KNN bridge
    generation cannot collide with gaps left by dropped self-loops or duplicates.
    """
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
        aliases.append(
            {
                "id": node.id,
                "label": node.label,
                "type": node.type,
                "source_span": node.source_span,
            }
        )
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
    reranker_client: RerankerClient | None = None,
) -> ExtractedGraph:
    """Resolve synonym nodes via embedding similarity and stitch isolated islands.

    The pipeline:

    1. Embed each node's label (+ source span + folded leaves).
    2. Coarse-filter high-risk candidate pairs with batched cosine similarity matrices.
    3. Fine-filter candidates with a cloud reranker (when enabled); only pairs whose
       reranker score exceeds ``reranker_threshold`` are merged.
    4. Merge each cluster into its highest-degree root, remapping edges.
    5. For remaining small components, add a weak ``SEMANTICALLY_RELATED_TO`` bridge
       to the nearest node in the largest component if similarity >= ``semantic_knn_threshold``.
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
        raise ValueError(f"Embedding count mismatch: {len(embeddings)} vectors for {len(graph.nodes)} nodes")

    embeddings_matrix = np.array(embeddings, dtype=np.float32)
    nodes_by_id = {node.id: node for node in graph.nodes}

    # 1. Stage 1 hard type firewall + Stage 2 matrix coarse-filter.
    #    Nodes are grouped by type; within each group we compute the full cosine
    #    similarity matrix with a single NumPy dot product and extract the
    #    upper-triangle pairs that exceed the dynamic threshold.  This replaces
    #    the previous O(N^2) Python double loop.
    node_ids = [node.id for node in graph.nodes]
    type_groups = _group_nodes_by_type(graph.nodes)
    coarse_pairs: list[tuple[str, str, float]] = []
    for node_type, indexed_nodes in type_groups.items():
        group_indices = [idx for idx, _ in indexed_nodes]
        group_nodes = [graph.nodes[idx] for idx in group_indices]
        if len(group_nodes) < 2:
            continue
        group_embeddings = embeddings_matrix[group_indices]
        threshold = settings.semantic_similarity_threshold_for(
            node_type,
            node_type,
            graph.paradigm.value,
        )
        coarse_pairs.extend(_coarse_filter_pairs(group_nodes, group_embeddings, threshold))

    # 2. Stage 3 cloud reranker fine-filter (optional but recommended).
    #    Only pairs whose reranker score is strictly above the threshold are
    #    promoted to TRUE_HOMOGENEOUS and merged via union-find.
    client = reranker_client or RerankerClient(settings)
    pair_texts = [
        (_node_text(nodes_by_id[node_id_i]), _node_text(nodes_by_id[node_id_j]))
        for node_id_i, node_id_j, _ in coarse_pairs
    ]
    try:
        rerank_scores = await client.rerank_pairs(pair_texts)
    except Exception as exc:
        logger.warning("semantic_clustering_rerank_failed", extra={"error": str(exc)})
        warnings = list(graph.warnings)
        warnings.append(f"SEMANTIC_CLUSTERING_RERANK_SKIPPED:{type(exc).__name__}")
        return graph.model_copy(update={"warnings": warnings})

    uf = _UnionFind()
    for (node_id_i, node_id_j, _coarse_score), rerank_score in zip(
        coarse_pairs, rerank_scores, strict=True
    ):
        if rerank_score > settings.reranker_threshold:
            uf.union(node_id_i, node_id_j)

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
    for node_id, emb in zip(node_ids, embeddings, strict=True):
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
