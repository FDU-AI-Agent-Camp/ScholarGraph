"""Unit tests for shared patrol helper modules."""

from __future__ import annotations

from backend.patrol.node_selection import select_primary_node
from backend.patrol.similarity import (
    cosine_similarity,
    derive_clash_aspect,
    derive_conflict_type,
    english_word_ratio,
    is_predominantly_english,
    normalize_label,
)
from backend.schemas.graph import GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm


def test_normalize_label_strips_and_lowercases() -> None:
    assert normalize_label("  PCA  ") == "pca"


def test_cosine_similarity_identical_vectors() -> None:
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_english_word_ratio_detects_predominantly_english_labels() -> None:
    assert is_predominantly_english("Does PCA improve classification accuracy?")
    assert not is_predominantly_english("PCA 是否提升分类准确率？")
    assert english_word_ratio("PCA 是否提升分类准确率？") < 0.5


def test_derive_conflict_type_and_clash_aspect() -> None:
    assert derive_conflict_type("论点 A", "论点 A") == "none"
    assert derive_conflict_type("论点 A", "论点 B") == "potential"
    assert derive_clash_aspect("历史制度主义", "历史制度主义") == "none"
    assert derive_clash_aspect("消费社会", "公共领域") == "analytical_framework"


def test_select_primary_node_prefers_rich_metadata_over_list_order() -> None:
    graph = UnifiedPaperGraph(
        paper_id="hss-001",
        paradigm=Paradigm.HSS,
        nodes=[
            GraphNode(id="n_sparse", label="Sparse", type="Thesis", data={}),
            GraphNode(
                id="n_rich",
                label="Rich thesis",
                type="Thesis",
                data={"description": "Detailed thesis statement"},
            ),
        ],
        edges=[],
    )
    selected = select_primary_node(graph.nodes, graph=graph)
    assert selected is not None
    assert selected.id == "n_rich"


def test_select_primary_node_uses_stable_id_tiebreak() -> None:
    graph = UnifiedPaperGraph(
        paper_id="hss-001",
        paradigm=Paradigm.HSS,
        nodes=[
            GraphNode(id="n_secondary", label="Thesis", type="Thesis", data={}),
            GraphNode(id="n_primary", label="Thesis", type="Thesis", data={}),
        ],
        edges=[],
    )
    selected = select_primary_node(graph.nodes, graph=graph)
    assert selected is not None
    assert selected.id == "n_primary"
