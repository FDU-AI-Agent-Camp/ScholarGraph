"""Convert graph structures into vector-indexable RAG evidence."""

from __future__ import annotations

from typing import Any

from backend.rag.models import PaperEntity, PaperRelation
from backend.schemas.graph import GraphNode, UnifiedPaperGraph

# Whitelist of node.data keys that carry business semantics suitable for embedding.
# Keys such as "source_span", "coords", "bbox" are intentionally excluded because
# they are noisy structural metadata, not semantic content.
ENTITY_SEMANTIC_KEYS = ("description", "summary", "rationale", "evidence")

# Maximum length of any single textual fragment pulled from node.data.
MAX_DATA_FRAGMENT_CHARS = 500


def graph_to_entities(paper_id: str, graph: UnifiedPaperGraph) -> list[PaperEntity]:
    """Convert graph nodes to entity evidence while preserving graph node IDs."""

    return [_node_to_entity(paper_id, node) for node in graph.nodes]


def graph_to_relations(paper_id: str, graph: UnifiedPaperGraph) -> list[PaperRelation]:
    """Convert graph edges to relation evidence while preserving graph edge IDs."""

    node_labels = {node.id: node.label for node in graph.nodes}
    relations: list[PaperRelation] = []
    for edge in graph.edges:
        source_label = node_labels.get(edge.source, edge.source)
        target_label = node_labels.get(edge.target, edge.target)
        description = _join_description_parts(
            [
                f"{source_label} --[{edge.type}]--> {target_label}.",
                f"Rationale: {edge.rationale}" if edge.rationale else "",
                f"Source span: {edge.source_span}" if edge.source_span else "",
            ]
        )
        relations.append(
            PaperRelation(
                relation_id=edge.id,
                paper_id=paper_id,
                source_id=edge.source,
                target_id=edge.target,
                relation_type=edge.type,
                description=description,
                rationale=edge.rationale,
                source_span=edge.source_span,
            )
        )
    return relations


def _node_to_entity(paper_id: str, node: GraphNode) -> PaperEntity:
    """Build a concise, semantic entity description from a graph node.

    The description is textualized from a whitelist of business-meaningful
    fields. Raw JSON serialization is never used, to keep embedding quality high.
    """

    source_span = _first_text(node.data.get("source_span"), node.data.get("span"))
    support_text = _extract_semantic_text(node.data)
    description = _join_description_parts(
        [
            f"{node.label} (type: {node.type}).",
            support_text,
        ]
    )
    return PaperEntity(
        entity_id=node.id,
        paper_id=paper_id,
        label=node.label,
        node_type=str(node.type),
        description=description,
        source_span=source_span,
    )


def _extract_semantic_text(data: dict[str, Any]) -> str:
    """Return a single business-meaningful sentence from whitelisted node data."""

    if not data:
        return ""

    fragments: list[str] = []
    for key in ENTITY_SEMANTIC_KEYS:
        value = data.get(key)
        text = _first_text(value)
        if text:
            # Avoid duplicating the same sentence under different keys.
            if text not in fragments:
                fragments.append(text)

    combined = " ".join(fragments)
    if len(combined) > MAX_DATA_FRAGMENT_CHARS:
        combined = combined[:MAX_DATA_FRAGMENT_CHARS].rsplit(" ", 1)[0] + "..."
    return combined


def _first_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _join_description_parts(parts: list[str | None]) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())
