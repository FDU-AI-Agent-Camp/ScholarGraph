# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Second-order graph dehydration: semantic clustering and island stitching."""

from __future__ import annotations

import logging
from collections import defaultdict

import numpy as np

from backend.config import Settings
from backend.graph._semantic_clustering_merge import (
    _add_knn_bridges,
    _elect_root,
    _merge_clusters,
)
from backend.graph._semantic_clustering_text import (
    _build_components,
    _coarse_filter_pairs,
    _compute_degrees,
    _cross_type_merge_allowed,
    _deduplicate_edges_by_type,
    _fuse_descriptions,
    _group_nodes_by_type,
    _node_text,
)
from backend.graph.merge_graphs import _UnionFind
from backend.llm.embeddings import EmbeddingClient
from backend.llm.reranker import RerankerClient
from backend.schemas.extract_phase import ExtractedGraph

logger = logging.getLogger(__name__)

# These private names are re-exported for existing unit tests.
__all__ = [
    "semantic_cluster_and_merge",
    "_add_knn_bridges",
    "_build_components",
    "_coarse_filter_pairs",
    "_compute_degrees",
    "_cross_type_merge_allowed",
    "_deduplicate_edges_by_type",
    "_elect_root",
    "_fuse_descriptions",
    "_group_nodes_by_type",
    "_merge_clusters",
    "_node_text",
]


async def semantic_cluster_and_merge(
    graph: ExtractedGraph,
    settings: Settings,
    *,
    embedding_client: EmbeddingClient | None = None,
    reranker_client: RerankerClient | None = None,
) -> ExtractedGraph:
    """Resolve synonym nodes via embedding similarity and stitch isolated islands."""
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

    uf = _UnionFind()
    if settings.reranker_enabled:
        client = reranker_client or RerankerClient(settings)
        pair_texts: list[tuple[str, str]] = []
        for node_id_i, node_id_j, _ in coarse_pairs:
            text_i = _node_text(nodes_by_id[node_id_i])
            text_j = _node_text(nodes_by_id[node_id_j])
            if node_id_i <= node_id_j:
                pair_texts.append((text_i, text_j))
            else:
                pair_texts.append((text_j, text_i))
        try:
            rerank_scores = await client.rerank_pairs(pair_texts)
        except Exception as exc:
            logger.warning("semantic_clustering_rerank_failed", extra={"error": str(exc)})
            warnings = list(graph.warnings)
            warnings.append(f"SEMANTIC_CLUSTERING_RERANK_SKIPPED:{type(exc).__name__}")
            return graph.model_copy(update={"warnings": warnings})

        for (node_id_i, node_id_j, _coarse_score), rerank_score in zip(coarse_pairs, rerank_scores, strict=True):
            if rerank_score > settings.reranker_threshold:
                uf.union(node_id_i, node_id_j)
    else:
        logger.warning(
            "semantic_clustering_reranker_disabled: falling back to coarse filter, "
            "merge fidelity may be degraded and over-merging is likely"
        )
        for node_id_i, node_id_j, _ in coarse_pairs:
            uf.union(node_id_i, node_id_j)

    clusters: dict[str, set[str]] = defaultdict(set)
    for node_id in node_ids:
        clusters[uf.find(node_id)].add(node_id)
    cluster_list = list(clusters.values())

    nodes_after_merge, edges_after_merge, id_map, merged_clusters = _merge_clusters(
        graph.nodes, graph.edges, cluster_list
    )

    root_to_embedding: dict[str, list[float]] = {}
    for node_id, emb in zip(node_ids, embeddings, strict=True):
        root_id = id_map[node_id]
        if root_id not in root_to_embedding:
            root_to_embedding[root_id] = emb
    merged_embeddings = [root_to_embedding[node.id] for node in nodes_after_merge]

    final_edges, bridges_added = _add_knn_bridges(
        nodes_after_merge,
        edges_after_merge,
        merged_embeddings,
        settings.semantic_knn_threshold_effective,
    )

    final_edges = _deduplicate_edges_by_type(final_edges)

    warnings = list(graph.warnings)
    if merged_clusters:
        warnings.append(f"SEMANTIC_CLUSTERS_MERGED:{merged_clusters}")
    if bridges_added:
        warnings.append(f"SEMANTIC_KNN_EDGES_ADDED:{bridges_added}")

    return graph.model_copy(update={"nodes": nodes_after_merge, "edges": final_edges, "warnings": warnings})
