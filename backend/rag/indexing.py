"""Convert graph structures into vector-indexable RAG evidence."""

from __future__ import annotations

import json
from typing import Any

from backend.rag.models import PaperEntity, PaperRelation
from backend.schemas.graph import GraphNode, UnifiedPaperGraph

ENTITY_TEXT_KEYS = ("rationale", "description", "source_span", "summary", "evidence")


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
    source_span = _first_text(node.data.get("source_span"), node.data.get("span"), node.data.get("evidence"))
    support_text = _first_text(*(node.data.get(key) for key in ENTITY_TEXT_KEYS))
    description = _join_description_parts(
        [
            f"{node.label} (type: {node.type}).",
            support_text,
            _compact_json(node.data) if not support_text and node.data else "",
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


def _first_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _join_description_parts(parts: list[str | None]) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
