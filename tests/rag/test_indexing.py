# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for graph-to-RAG-evidence conversion."""

from __future__ import annotations

import pytest
from backend.rag.indexing import (
    ENTITY_SEMANTIC_KEYS,
    MAX_DATA_FRAGMENT_CHARS,
    _extract_semantic_text,
    _first_text,
    _join_description_parts,
    graph_to_entities,
    graph_to_relations,
)
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


class TestExtractSemanticText:
    """Strict unit tests for the whitelist-based textualization helper."""

    def test_returns_empty_for_empty_data(self) -> None:
        assert _extract_semantic_text({}) == ""

    def test_returns_empty_for_none_data(self) -> None:
        assert _extract_semantic_text(None) == ""  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "key",
        [
            "source_span",
            "bbox",
            "coords",
            "page",
            "x",
            "y",
            "raw_json",
            "extra",
            "metadata",
        ],
    )
    def test_rejects_non_whitelisted_keys(self, key: str) -> None:
        assert _extract_semantic_text({key: "This should be ignored."}) == ""

    @pytest.mark.parametrize("key", list(ENTITY_SEMANTIC_KEYS))
    def test_accepts_whitelisted_keys(self, key: str) -> None:
        assert _extract_semantic_text({key: "Semantic content."}) == "Semantic content."

    def test_rejects_non_string_values(self) -> None:
        data = {
            "description": 123,
            "summary": ["not", "a", "string"],
            "rationale": {"nested": "object"},
            "evidence": None,
        }
        assert _extract_semantic_text(data) == ""

    def test_rejects_blank_strings(self) -> None:
        data = {
            "description": "   ",
            "summary": "",
            "rationale": "\t\n",
        }
        assert _extract_semantic_text(data) == ""

    def test_joins_multiple_whitelisted_values_in_priority_order(self) -> None:
        data = {
            "evidence": "Used in Table 1.",
            "summary": "A linear technique.",
            "description": "Principal Component Analysis.",
            "rationale": "Reduces dimensionality.",
        }
        result = _extract_semantic_text(data)
        expected = "Principal Component Analysis. A linear technique. Reduces dimensionality. Used in Table 1."
        assert result == expected

    def test_deduplicates_identical_values(self) -> None:
        data = {
            "description": "Reduces dimensionality.",
            "summary": "Reduces dimensionality.",
            "rationale": "Reduces dimensionality.",
            "evidence": "Reduces dimensionality.",
        }
        assert _extract_semantic_text(data) == "Reduces dimensionality."

    def test_truncates_long_combined_text(self) -> None:
        long_text = "word " * 200
        data = {
            "description": long_text,
            "summary": long_text,
        }
        result = _extract_semantic_text(data)
        assert len(result) <= MAX_DATA_FRAGMENT_CHARS + 3  # allow trailing "..."
        assert result.endswith("...")

    def test_preserves_unicode_and_special_characters(self) -> None:
        data = {
            "description": "PCA（主成分分析）用于降维。",
            "summary": "α + β → γ",
        }
        result = _extract_semantic_text(data)
        assert "PCA（主成分分析）用于降维。" in result
        assert "α + β → γ" in result


class TestFirstText:
    def test_returns_first_non_empty_string(self) -> None:
        assert _first_text(None, "", "   ", "first", "second") == "first"

    def test_returns_none_when_no_strings(self) -> None:
        assert _first_text(None, 123, ["list"], {"key": "value"}, "") is None

    def test_strips_whitespace(self) -> None:
        assert _first_text("  padded  ") == "padded"


class TestJoinDescriptionParts:
    def test_skips_none_and_blank_values(self) -> None:
        assert _join_description_parts([None, "", "   ", "a", None, "b"]) == "a b"

    def test_returns_empty_when_all_blank(self) -> None:
        assert _join_description_parts([None, "", "   "]) == ""


class TestEntityDescriptionStrictness:
    """End-to-end strictness tests at the entity level."""

    def test_no_json_characters_in_description(self) -> None:
        graph = UnifiedPaperGraph(
            paper_id="paper-json-free",
            paradigm=Paradigm.STEM,
            nodes=[
                GraphNode(
                    id="n_noisy",
                    label="Noisy node",
                    type=NodeType.CLAIM,
                    data={
                        "description": "Real content.",
                        "source_span": "span text",
                        "bbox": {"x": 1, "y": 2},
                        "nested": {"foo": "bar"},
                        "list": [1, 2, 3],
                    },
                )
            ],
            edges=[],
        )

        description = graph_to_entities("paper-json-free", graph)[0].description

        assert "Real content." in description
        # Structural JSON tokens must never appear; ':' is allowed because the
        # fallback label format uses "(type: Claim)".
        for char in "{}[]\"'":
            assert char not in description, f"JSON character {char!r} found in description"

    def test_only_label_and_type_when_no_semantic_data(self) -> None:
        graph = UnifiedPaperGraph(
            paper_id="paper-minimal",
            paradigm=Paradigm.STEM,
            nodes=[
                GraphNode(
                    id="n_minimal",
                    label="Core claim",
                    type=NodeType.CLAIM,
                    data={"source_span": "ignored", "bbox": {"x": 1}},
                )
            ],
            edges=[],
        )

        description = graph_to_entities("paper-minimal", graph)[0].description
        assert description == "Core claim (type: Claim)."

    def test_whitelist_order_overrides_arbitrary_data_order(self) -> None:
        graph = UnifiedPaperGraph(
            paper_id="paper-order",
            paradigm=Paradigm.STEM,
            nodes=[
                GraphNode(
                    id="n_ordered",
                    label="Ordered",
                    type=NodeType.METHOD,
                    data={
                        "evidence": "E",
                        "rationale": "R",
                        "summary": "S",
                        "description": "D",
                    },
                )
            ],
            edges=[],
        )

        description = graph_to_entities("paper-order", graph)[0].description
        # Whitelist order is description, summary, rationale, evidence.
        assert description == "Ordered (type: Method). D S R E"
