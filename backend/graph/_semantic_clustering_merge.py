"""Cluster merge and K-NN island bridging for semantic clustering."""

from __future__ import annotations

from backend.graph._semantic_clustering_text import (
    _DEFAULT_ROOT_PRIORITY,
    _ROOT_TYPE_PRIORITY,
    _SEMANTIC_BRIDGE_LABEL,
    _SEMANTIC_BRIDGE_TYPE,
    _build_components,
    _compute_degrees,
    _cosine_similarity,
    _fuse_descriptions,
    _next_edge_index,
)
from backend.schemas.extract_phase import ExtractedEdge, ExtractedNode


def _elect_root(cluster_ids: set[str], degrees: dict[str, int], nodes_by_id: dict[str, ExtractedNode]) -> str:
    """Elect the canonical root for a semantic cluster."""

    def _score(node_id: str) -> tuple[int, int, float, str]:
        node = nodes_by_id[node_id]
        priority = _ROOT_TYPE_PRIORITY.get(node.type, _DEFAULT_ROOT_PRIORITY)
        return (priority, -degrees.get(node_id, 0), -node.confidence, node_id)

    return min(cluster_ids, key=_score)


def _richer_edge(a: ExtractedEdge, b: ExtractedEdge) -> ExtractedEdge:
    """Keep the edge that carries more semantic information."""
    a_rationale_len = len(a.rationale or "")
    b_rationale_len = len(b.rationale or "")
    if b_rationale_len > a_rationale_len:
        return b
    if a_rationale_len > b_rationale_len:
        return a
    if b.source_span and len(b.source_span) > len(a.source_span or ""):
        return b
    return a


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

        folded = node.data.get("folded_leaves")
        if isinstance(folded, list):
            existing_folded = new_data.get("folded_leaves", [])
            if not isinstance(existing_folded, list):
                existing_folded = []
            existing_folded.extend(folded)
            new_data["folded_leaves"] = existing_folded

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

    for cluster in clusters:
        if len(cluster) <= 1:
            continue
        root_id = id_map[next(iter(cluster))]
        descriptions = [desc for node_id in cluster if (desc := nodes_by_id[node_id].description) is not None]
        fused = _fuse_descriptions(descriptions)
        if fused:
            existing = new_nodes_by_id[root_id]
            new_nodes_by_id[root_id] = existing.model_copy(update={"description": fused})

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
