"""Unit tests for backend.patrol.samples eval graph seeds."""

from backend.graph.store import GraphStore
from backend.patrol.lens_clash import analytical_lens_nodes
from backend.patrol.method_overlap import method_nodes
from backend.patrol.samples import (
    CORPUS_HSS_PAPER_IDS,
    CORPUS_PATROL_LENSES,
    CORPUS_STEM_PAPER_IDS,
    build_hss_graph_with_lens,
    seed_corpus_patrol_graphs,
    seed_patrol_graphs,
    seed_stem_patrol_graphs,
)


def test_corpus_constants_cover_two_hss_papers() -> None:
    assert len(CORPUS_HSS_PAPER_IDS) == 2
    assert set(CORPUS_HSS_PAPER_IDS) == set(CORPUS_PATROL_LENSES)


def test_build_hss_graph_with_lens_has_analytical_lens() -> None:
    graph = build_hss_graph_with_lens(
        "hss-001",
        lens_id="n_lens",
        lens_label="测试视角",
    )
    lenses = analytical_lens_nodes(graph)
    assert len(lenses) == 1
    assert lenses[0].id == "n_lens"
    assert graph.paradigm.value == "HSS"


def test_seed_patrol_graphs_round_trip_via_graph_store(tmp_path) -> None:
    store_dir = tmp_path / "graphs"
    seed_patrol_graphs(
        store_dir,
        {
            "hss-001": ("n_a", "视角 A"),
            "hss-002": ("n_b", "视角 B"),
        },
    )
    store = GraphStore(base_dir=store_dir)
    loaded_a = store.load("hss-001")
    loaded_b = store.load("hss-002")
    assert loaded_a is not None and loaded_b is not None
    assert analytical_lens_nodes(loaded_a)[0].label == "视角 A"
    assert analytical_lens_nodes(loaded_b)[0].label == "视角 B"


def test_seed_stem_patrol_graphs_writes_method_and_question_nodes(tmp_path) -> None:
    store_dir = tmp_path / "graphs"
    seed_stem_patrol_graphs(store_dir)
    store = GraphStore(base_dir=store_dir)
    for paper_id in CORPUS_STEM_PAPER_IDS:
        graph = store.load(paper_id)
        assert graph is not None
        assert graph.paradigm.value == "STEM"
        assert len(method_nodes(graph)) >= 1
        labels = {node.label for node in graph.nodes}
        assert "PCA 是否提升 MNIST 分类准确率？" in labels


def test_seed_corpus_patrol_graphs_matches_eval_lenses(tmp_path) -> None:
    store_dir = tmp_path / "graphs"
    seed_corpus_patrol_graphs(store_dir)
    store = GraphStore(base_dir=store_dir)
    for paper_id, (_node_id, label) in CORPUS_PATROL_LENSES.items():
        graph = store.load(paper_id)
        assert graph is not None
        assert analytical_lens_nodes(graph)[0].label == label
