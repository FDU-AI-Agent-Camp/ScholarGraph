# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for semantic cluster merge / KNN bridge primitives (SC-R1 post-rerank path)."""

from __future__ import annotations

from backend.graph._semantic_clustering_merge import _add_knn_bridges, _merge_clusters
from backend.schemas.extract_phase import ExtractedEdge, ExtractedNode


def _node(node_id: str, *, label: str, node_type: str = "Method", confidence: float = 1.0) -> ExtractedNode:
    return ExtractedNode(id=node_id, label=label, type=node_type, confidence=confidence)


def test_merge_clusters_singleton_clusters_leave_graph_unchanged() -> None:
    """When reranker rejects all pairs (SC-R1), merge step is a no-op."""
    nodes = [
        _node("n1", label="Adam"),
        _node("n2", label="Adam Optimizer"),
    ]
    edges = [
        ExtractedEdge(id="e1", source="n1", target="n2", label="uses", type="USES_METHOD"),
    ]
    merged_nodes, merged_edges, id_map, merged_count = _merge_clusters(
        nodes,
        edges,
        clusters=[{"n1"}, {"n2"}],
    )
    assert merged_count == 0
    assert {node.id for node in merged_nodes} == {"n1", "n2"}
    assert id_map == {"n1": "n1", "n2": "n2"}
    assert len(merged_edges) == 1
    assert merged_edges[0].source == "n1"


def test_merge_clusters_collapses_cluster_and_keeps_richer_parallel_edge() -> None:
    nodes = [
        _node("n1", label="Adam", confidence=0.7),
        _node("n2", label="Adam Optimizer", confidence=0.9),
        _node("n3", label="CNN", confidence=0.8),
    ]
    edges = [
        ExtractedEdge(
            id="e1",
            source="n1",
            target="n3",
            label="uses",
            type="USES_METHOD",
            rationale="short",
        ),
        ExtractedEdge(
            id="e2",
            source="n2",
            target="n3",
            label="uses",
            type="USES_METHOD",
            rationale="much longer semantic rationale",
        ),
    ]
    merged_nodes, merged_edges, id_map, merged_count = _merge_clusters(
        nodes,
        edges,
        clusters=[{"n1", "n2"}, {"n3"}],
    )
    assert merged_count == 1
    assert id_map["n1"] == id_map["n2"] == "n2"
    assert len(merged_nodes) == 2
    root = next(node for node in merged_nodes if node.id == "n2")
    alias_ids = {alias["id"] for alias in root.data.get("semantic_aliases", [])}
    assert alias_ids == {"n1"}
    assert len(merged_edges) == 1
    assert merged_edges[0].rationale == "much longer semantic rationale"


def test_add_knn_bridges_skips_when_similarity_below_threshold() -> None:
    nodes = [
        _node("main", label="Main"),
        _node("iso", label="Island"),
    ]
    edges = [
        ExtractedEdge(id="e1", source="main", target="main", label="self", type="USES_METHOD"),
    ]
    embeddings = [
        [1.0, 0.0],
        [0.0, 1.0],
    ]
    result_edges, bridges_added = _add_knn_bridges(nodes, edges, embeddings, knn_threshold=0.85)
    assert bridges_added == 0
    assert len(result_edges) == 1


def test_add_knn_bridges_adds_edge_at_threshold() -> None:
    nodes = [
        _node("main1", label="Main A"),
        _node("main2", label="Main B"),
        _node("iso", label="Island"),
    ]
    edges = [
        ExtractedEdge(id="e1", source="main1", target="main2", label="related", type="USES_METHOD"),
    ]
    embeddings = [
        [1.0, 0.0],
        [0.99, 0.01],
        [1.0, 0.0],
    ]
    result_edges, bridges_added = _add_knn_bridges(nodes, edges, embeddings, knn_threshold=1.0)
    assert bridges_added == 1
    bridge = next(edge for edge in result_edges if edge.type == "SEMANTICALLY_RELATED_TO")
    assert {bridge.source, bridge.target} == {"iso", "main1"}
    assert bridge.data.get("semantic_similarity") == 1.0


def test_add_knn_bridges_noop_for_single_component() -> None:
    nodes = [_node("a", label="A"), _node("b", label="B")]
    edges = [
        ExtractedEdge(id="e1", source="a", target="b", label="related", type="USES_METHOD"),
    ]
    embeddings = [[1.0, 0.0], [0.9, 0.1]]
    result_edges, bridges_added = _add_knn_bridges(nodes, edges, embeddings, knn_threshold=0.5)
    assert bridges_added == 0
    assert len(result_edges) == 1
