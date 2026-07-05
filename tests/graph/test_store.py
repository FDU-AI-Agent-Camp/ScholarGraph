"""Tests for graph store and G6 export (BE-3)."""

import json
from pathlib import Path

import pytest
from backend.graph.store import GraphStore
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm


@pytest.fixture
def hss_graph() -> UnifiedPaperGraph:
    """Minimal HSS graph matching the shape of docs/api/fixtures/graph-hss.json."""
    return UnifiedPaperGraph(
        paper_id="hss-001",
        paradigm=Paradigm.HSS,
        nodes=[
            GraphNode(id="n1", label="核心论点", type="Thesis"),
            GraphNode(id="n2", label="分论点：制度路径依赖", type="SubArgument"),
            GraphNode(id="n_lens", label="历史制度主义", type="AnalyticalLens"),
        ],
        edges=[
            GraphEdge(
                id="e1",
                source="n2",
                target="n1",
                label="SUB_ARGUMENT_OF",
                type="SUB_ARGUMENT_OF",
            ),
        ],
    )


@pytest.fixture
def store(tmp_path: Path) -> GraphStore:
    """GraphStore pointed at a temp directory."""
    return GraphStore(base_dir=tmp_path)


# ---------------------------------------------------------------------------
# to_g6()
# ---------------------------------------------------------------------------


class TestToG6:
    def test_output_shape_matches_g6_v5(self, hss_graph: UnifiedPaperGraph) -> None:
        result = GraphStore.to_g6(hss_graph)
        assert "nodes" in result
        assert "edges" in result
        assert isinstance(result["nodes"], list)
        assert isinstance(result["edges"], list)

    def test_nodes_have_g6_data_structure(self, hss_graph: UnifiedPaperGraph) -> None:
        result = GraphStore.to_g6(hss_graph)
        for node in result["nodes"]:
            assert "id" in node
            assert "data" in node
            assert "label" in node["data"]
            assert "type" in node["data"]

    def test_edges_have_g6_data_structure(self, hss_graph: UnifiedPaperGraph) -> None:
        result = GraphStore.to_g6(hss_graph)
        for edge in result["edges"]:
            assert "id" in edge
            assert "source" in edge
            assert "target" in edge
            assert "data" in edge
            assert "label" in edge["data"]
            assert "type" in edge["data"]

    def test_node_count_preserved(self, hss_graph: UnifiedPaperGraph) -> None:
        result = GraphStore.to_g6(hss_graph)
        assert len(result["nodes"]) == len(hss_graph.nodes)

    def test_edge_count_preserved(self, hss_graph: UnifiedPaperGraph) -> None:
        result = GraphStore.to_g6(hss_graph)
        assert len(result["edges"]) == len(hss_graph.edges)

    def test_extra_node_data_merged(self) -> None:
        graph = UnifiedPaperGraph(
            paper_id="test",
            paradigm=Paradigm.HSS,
            nodes=[GraphNode(id="n1", label="L", type="Thesis", data={"extra": 42})],
            edges=[],
        )
        result = GraphStore.to_g6(graph)
        assert result["nodes"][0]["data"]["extra"] == 42


# ---------------------------------------------------------------------------
# save / load round-trip
# ---------------------------------------------------------------------------


class TestSaveLoad:
    def test_round_trip(self, store: GraphStore, hss_graph: UnifiedPaperGraph) -> None:
        store.save(hss_graph)
        loaded = store.load("hss-001")
        assert loaded is not None
        assert loaded.paper_id == hss_graph.paper_id
        assert loaded.paradigm == hss_graph.paradigm
        assert len(loaded.nodes) == len(hss_graph.nodes)
        assert len(loaded.edges) == len(hss_graph.edges)

    def test_load_unknown_returns_none(self, store: GraphStore) -> None:
        assert store.load("nonexistent") is None

    def test_delete_removes_persisted_graph(self, store: GraphStore, hss_graph: UnifiedPaperGraph) -> None:
        store.save(hss_graph)
        assert store.delete("hss-001") is True
        assert store.load("hss-001") is None
        assert store.delete("hss-001") is False

    def test_save_is_json_serializable(self, store: GraphStore, hss_graph: UnifiedPaperGraph, tmp_path: Path) -> None:
        store.save(hss_graph)
        path = tmp_path / "hss-001.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert raw["paper_id"] == "hss-001"
        assert raw["paradigm"] == "HSS"
