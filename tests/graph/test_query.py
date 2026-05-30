"""Tests for GraphQuery subgraph extraction (BE-3)."""

import pytest

from backend.graph.query import GraphQuery
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm


@pytest.fixture
def hss_graph() -> UnifiedPaperGraph:
    """HSS graph with a realistic argumentation chain."""
    return UnifiedPaperGraph(
        paper_id="hss-001",
        paradigm=Paradigm.HSS,
        nodes=[
            GraphNode(id="n1", label="核心论点：数字劳动加剧社会不平等", type="Thesis"),
            GraphNode(id="n2", label="分论点1：平台算法强化了劳动控制", type="SubArgument"),
            GraphNode(id="n3", label="分论点2：零工经济削弱了劳动者议价能力", type="SubArgument"),
            GraphNode(id="n4", label="分论点3：社会保障体系滞后于劳动形态变化", type="SubArgument"),
            GraphNode(id="ctx1", label="马克思劳动异化理论", type="IntellectualContext"),
            GraphNode(id="lens1", label="政治经济学批判", type="AnalyticalLens"),
            GraphNode(id="obj1", label="某外卖平台骑手访谈记录（2023）", type="ObjectOrData"),
        ],
        edges=[
            GraphEdge(id="e1", source="n2", target="n1", label="SUB_ARGUMENT_OF", type="SUB_ARGUMENT_OF"),
            GraphEdge(id="e2", source="n3", target="n1", label="SUB_ARGUMENT_OF", type="SUB_ARGUMENT_OF"),
            GraphEdge(id="e3", source="n4", target="n1", label="SUB_ARGUMENT_OF", type="SUB_ARGUMENT_OF"),
            GraphEdge(id="e4", source="n1", target="ctx1", label="CHALLENGES", type="CHALLENGES"),
            GraphEdge(id="e5", source="obj1", target="lens1", label="EXAMINES_THROUGH", type="EXAMINES_THROUGH"),
        ],
    )


@pytest.fixture
def stem_graph() -> UnifiedPaperGraph:
    """Minimal STEM graph."""
    return UnifiedPaperGraph(
        paper_id="stem-001",
        paradigm=Paradigm.STEM,
        nodes=[
            GraphNode(id="rq1", label="如何提升LLM推理效率？", type="ResearchQuestion"),
            GraphNode(id="m1", label="Speculative Decoding", type="Method"),
            GraphNode(id="c1", label="SpecDec 比自回归解码快 2.3×", type="Claim"),
            GraphNode(id="ds1", label="GSM8K", type="Dataset"),
            GraphNode(id="ev1", label="端到端延迟测量", type="Evidence"),
        ],
        edges=[
            GraphEdge(id="e1", source="c1", target="ev1", label="SUPPORTED_BY", type="SUPPORTED_BY"),
            GraphEdge(id="e2", source="m1", target="ds1", label="EVALUATED_ON", type="EVALUATED_ON"),
        ],
    )


class TestSubgraphForQuestion:
    def test_hss_summary_question_finds_thesis(self, hss_graph: UnifiedPaperGraph) -> None:
        """A summary-scale question should surface the Thesis node."""
        query = GraphQuery()
        result = query.subgraph_for_question(hss_graph, "这篇论文的核心论点是什么？")
        node_ids = {n["id"] for n in result["nodes"]}
        assert "n1" in node_ids

    def test_hss_detail_question_finds_subarguments(self, hss_graph: UnifiedPaperGraph) -> None:
        """A detail-scale question about a sub-argument should find it."""
        query = GraphQuery()
        result = query.subgraph_for_question(hss_graph, "分论点2如何支撑核心论点？")
        node_ids = {n["id"] for n in result["nodes"]}
        assert "n1" in node_ids
        assert "n3" in node_ids

    def test_hss_verification_question_finds_lens(self, hss_graph: UnifiedPaperGraph) -> None:
        """A verification question about theoretical lens should match."""
        query = GraphQuery()
        result = query.subgraph_for_question(hss_graph, "核心论点通过哪些材料、经何种理论视角被论证？")
        node_ids = {n["id"] for n in result["nodes"]}
        assert "lens1" in node_ids or "obj1" in node_ids

    def test_stem_question_finds_relevant_nodes(self, stem_graph: UnifiedPaperGraph) -> None:
        query = GraphQuery()
        result = query.subgraph_for_question(stem_graph, "SpecDec 在什么数据集上做了评测？")
        node_ids = {n["id"] for n in result["nodes"]}
        assert "ds1" in node_ids

    def test_returns_valid_dict_structure(self, hss_graph: UnifiedPaperGraph) -> None:
        query = GraphQuery()
        result = query.subgraph_for_question(hss_graph, "分论点")
        assert "nodes" in result
        assert "edges" in result
        for n in result["nodes"]:
            assert "id" in n
            assert "label" in n
        for e in result["edges"]:
            assert "source" in e
            assert "target" in e

    def test_unknown_question_returns_fallback(self, hss_graph: UnifiedPaperGraph) -> None:
        """A question with no keyword match should return the fallback subgraph."""
        query = GraphQuery()
        result = query.subgraph_for_question(hss_graph, "xyzzy")
        node_ids = {n["id"] for n in result["nodes"]}
        assert len(node_ids) > 0
        assert "n1" in node_ids

    def test_two_hop_expansion_collects_edges(self, hss_graph: UnifiedPaperGraph) -> None:
        """Matching a SubArgument should also pull in connected IntellectualContext via Thesis."""
        query = GraphQuery()
        result = query.subgraph_for_question(hss_graph, "分论点1")
        node_ids = {n["id"] for n in result["nodes"]}
        edge_ids = {e["id"] for e in result["edges"]}
        assert "n2" in node_ids
        assert "n1" in node_ids
        assert "ctx1" in node_ids
        assert "e1" in edge_ids
        assert "e4" in edge_ids

    def test_empty_graph_returns_empty_result(self) -> None:
        graph = UnifiedPaperGraph(paper_id="empty", paradigm=Paradigm.HSS, nodes=[], edges=[])
        query = GraphQuery()
        result = query.subgraph_for_question(graph, "核心论点")
        assert result["nodes"] == []
        assert result["edges"] == []
