"""Unit tests for graph-to-RAG-evidence conversion."""

from __future__ import annotations

from backend.rag.indexing import graph_to_entities, graph_to_relations
from backend.schemas.graph import GraphEdge, GraphNode, NodeType, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm


def _sample_graph() -> UnifiedPaperGraph:
    return UnifiedPaperGraph(
        paper_id="paper-graph",
        paradigm=Paradigm.STEM,
        nodes=[
            GraphNode(
                id="n_method",
                label="Hybrid chunker",
                type=NodeType.METHOD,
                data={"rationale": "Uses section-aware splitting before vector indexing."},
            ),
            GraphNode(id="n_claim", label="Improves evidence retrieval", type=NodeType.CLAIM),
            GraphNode(id="n_evidence", label="Ablation table", type=NodeType.EVIDENCE),
        ],
        edges=[
            GraphEdge(
                id="e_supports",
                source="n_evidence",
                target="n_claim",
                label="SUPPORTS",
                type="SUPPORTS",
                rationale="The ablation table reports higher citation precision.",
                source_span="Table 2 reports citation precision improvements.",
            )
        ],
    )


def test_graph_to_entities_preserves_node_ids_and_builds_descriptions() -> None:
    entities = graph_to_entities("paper-graph", _sample_graph())

    method = next(entity for entity in entities if entity.entity_id == "n_method")
    assert method.paper_id == "paper-graph"
    assert method.label == "Hybrid chunker"
    assert method.node_type == "Method"
    assert "section-aware splitting" in method.description


def test_graph_to_relations_preserves_edge_ids_and_labels_context() -> None:
    relations = graph_to_relations("paper-graph", _sample_graph())

    assert len(relations) == 1
    relation = relations[0]
    assert relation.relation_id == "e_supports"
    assert relation.source_id == "n_evidence"
    assert relation.target_id == "n_claim"
    assert relation.relation_type == "SUPPORTS"
    assert "Ablation table --[SUPPORTS]--> Improves evidence retrieval" in relation.description
    assert "citation precision" in relation.description


def test_graph_to_entities_uses_label_and_type_as_minimal_fallback() -> None:
    graph = UnifiedPaperGraph(
        paper_id="paper-empty",
        paradigm=Paradigm.STEM,
        nodes=[GraphNode(id="n_claim", label="Improves retrieval", type=NodeType.CLAIM, data={})],
        edges=[],
    )

    entities = graph_to_entities("paper-empty", graph)

    assert entities[0].description == "Improves retrieval (type: Claim)."


def test_graph_to_entities_excludes_noise_fields_from_description() -> None:
    """source_span and structural metadata must not pollute the embedding text."""

    graph = UnifiedPaperGraph(
        paper_id="paper-noise",
        paradigm=Paradigm.STEM,
        nodes=[
            GraphNode(
                id="n_method",
                label="PCA",
                type=NodeType.METHOD,
                data={
                    "rationale": "Reduces dimensionality.",
                    "source_span": "We apply PCA to reduce dimensions.",
                    "bbox": {"x": 10, "y": 20},
                    "coords": [1, 2, 3],
                },
            )
        ],
        edges=[],
    )

    entity = graph_to_entities("paper-noise", graph)[0]

    assert "Reduces dimensionality." in entity.description
    assert "source_span" not in entity.description
    assert "bbox" not in entity.description
    assert "coords" not in entity.description
    assert "{" not in entity.description  # no raw JSON


def test_graph_to_entities_deduplicates_repeated_text() -> None:
    graph = UnifiedPaperGraph(
        paper_id="paper-dedup",
        paradigm=Paradigm.STEM,
        nodes=[
            GraphNode(
                id="n_method",
                label="PCA",
                type=NodeType.METHOD,
                data={
                    "rationale": "Reduces dimensionality.",
                    "description": "Reduces dimensionality.",
                    "summary": "Reduces dimensionality.",
                },
            )
        ],
        edges=[],
    )

    entity = graph_to_entities("paper-dedup", graph)[0]

    # The sentence should appear exactly once, not three times.
    assert entity.description.count("Reduces dimensionality.") == 1


def test_graph_to_entities_prioritizes_whitelisted_semantic_keys() -> None:
    graph = UnifiedPaperGraph(
        paper_id="paper-priority",
        paradigm=Paradigm.STEM,
        nodes=[
            GraphNode(
                id="n_method",
                label="PCA",
                type=NodeType.METHOD,
                data={
                    "description": "Principal Component Analysis.",
                    "summary": "A linear dimensionality reduction technique.",
                    "evidence": "Used in Table 1.",
                },
            )
        ],
        edges=[],
    )

    entity = graph_to_entities("paper-priority", graph)[0]

    assert "Principal Component Analysis." in entity.description
    assert "A linear dimensionality reduction technique." in entity.description
    assert "Used in Table 1." in entity.description
