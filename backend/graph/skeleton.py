"""Hard downsampling for frontend-facing graph skeleton views."""

from __future__ import annotations

from collections import deque

from backend.schemas.graph import GraphEdge, UnifiedPaperGraph

DEFAULT_MAX_SKELETON_NODES = 300


def build_skeleton_graph(
    graph: UnifiedPaperGraph,
    *,
    max_nodes: int = DEFAULT_MAX_SKELETON_NODES,
) -> UnifiedPaperGraph:
    """Return a downsized skeleton graph.

    Pipeline:

    1. Keep only the largest connected component (giant component).
    2. If the giant component still exceeds ``max_nodes``, keep the top-N
       highest-degree nodes and the edges between them.

    This is the API-level last line of defense against oversized graphs.
    """
    if not graph.nodes:
        return graph

    node_by_id = {node.id: node for node in graph.nodes}
    node_ids = set(node_by_id.keys())

    adj: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    incident_edges: dict[str, list[GraphEdge]] = {node_id: [] for node_id in node_ids}
    for edge in graph.edges:
        if edge.source in node_ids and edge.target in node_ids:
            adj[edge.source].add(edge.target)
            adj[edge.target].add(edge.source)
            incident_edges[edge.source].append(edge)
            incident_edges[edge.target].append(edge)

    # 1. Extract the giant component.
    visited: set[str] = set()
    components: list[set[str]] = []
    for node_id in node_ids:
        if node_id in visited:
            continue
        queue = deque([node_id])
        visited.add(node_id)
        component: set[str] = set()
        while queue:
            current = queue.popleft()
            component.add(current)
            for neighbor in adj[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        components.append(component)

    if not components:
        return graph.model_copy(update={"nodes": [], "edges": []})

    components.sort(key=len, reverse=True)
    giant_component = components[0]

    # 2. Degree-centrality cutoff if still too large.
    if len(giant_component) > max_nodes:
        degrees = {node_id: len(incident_edges[node_id]) for node_id in giant_component}
        sorted_nodes = sorted(giant_component, key=lambda nid: (-degrees[nid], nid))
        giant_component = set(sorted_nodes[:max_nodes])

    kept_node_ids = giant_component
    kept_nodes = [node for node in graph.nodes if node.id in kept_node_ids]
    kept_edges = [
        edge for edge in graph.edges
        if edge.source in kept_node_ids and edge.target in kept_node_ids
    ]

    return graph.model_copy(update={"nodes": kept_nodes, "edges": kept_edges})
