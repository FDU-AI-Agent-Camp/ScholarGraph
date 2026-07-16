"""Tests for V2 multi-type citation parsing (rag-qa-evaluation).

Covers:
- ``_CITE_RE`` regex matching all four citation types.
- ``dispatch_citation`` correct event shapes.
- ``_build_edge_label_cache`` auto-joined labels.
- ``format_retrieval_context`` prompt-section generation.
- Mixed citation types in a single LLM stream.
"""

from __future__ import annotations

import pytest
from backend.graph.qa import (
    _CITE_RE,
    _build_edge_label_cache,
    _split_incomplete_cite,
)
from backend.graph.qa_v2 import (
    build_chunk_text_cache,
    dispatch_citation,
    format_retrieval_context,
)
from backend.rag.models import (
    QuestionScale,
    RetrievalContext,
    RetrievedChunk,
    RetrievedEntity,
    RetrievedRelation,
)
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm

# ---------------------------------------------------------------------------
# Regex — single-marker parsing
# ---------------------------------------------------------------------------


class TestCiteRegex:
    """Cover all four citation marker formats."""

    def test_matches_bare_node_citation(self) -> None:
        match = _CITE_RE.search("text [CITE:n1] more")
        assert match is not None
        assert match.group(1) == "" or match.group(1) is None
        # group(2) is the actual value
        assert match.group(2) == "n1"

    def test_matches_edge_citation(self) -> None:
        match = _CITE_RE.search("text [CITE:edge:e_supports_01] end")
        assert match is not None
        assert match.group(1) == "edge:"
        assert match.group(2) == "e_supports_01"

    def test_matches_chunk_citation(self) -> None:
        match = _CITE_RE.search("text [CITE:chunk:hss-001-00001] end")
        assert match is not None
        assert match.group(1) == "chunk:"
        assert match.group(2) == "hss-001-00001"

    def test_matches_page_citation(self) -> None:
        match = _CITE_RE.search("text [CITE:page:12] end")
        assert match is not None
        assert match.group(1) == "page:"
        assert match.group(2) == "12"

    def test_matches_page_numeric_only(self) -> None:
        match = _CITE_RE.search("[CITE:page:42]")
        assert match is not None
        assert match.group(1) == "page:"
        assert match.group(2) == "42"

    def test_multiple_citations_in_one_line(self) -> None:
        text = "[CITE:n1] 与 [CITE:edge:e1] 及 [CITE:chunk:c1]"
        matches = list(_CITE_RE.finditer(text))
        assert len(matches) == 3
        assert matches[0].group(2) == "n1"
        assert matches[1].group(1) == "edge:"
        assert matches[1].group(2) == "e1"
        assert matches[2].group(1) == "chunk:"
        assert matches[2].group(2) == "c1"


# ---------------------------------------------------------------------------
# Incomplete citation splitting
# ---------------------------------------------------------------------------


class TestSplitIncompleteCite:
    """Ensure partial [CITE:... markers that span chunks are held correctly."""

    def test_complete_bare_cite_returns_none(self) -> None:
        assert _split_incomplete_cite("[CITE:n1]") is None

    def test_partial_cite_delim_held(self) -> None:
        result = _split_incomplete_cite("hello [CITE")
        assert result is not None
        safe, held = result
        assert safe == "hello "
        assert held == "[CITE"

    def test_partial_cite_with_type_held(self) -> None:
        result = _split_incomplete_cite("text [CITE:edge:")
        assert result is not None
        safe, held = result
        assert safe == "text "
        assert held == "[CITE:edge:"

    def test_partial_cite_with_chunk_held(self) -> None:
        result = _split_incomplete_cite("text [CITE:chunk:")
        assert result is not None
        safe, held = result
        assert safe == "text "
        assert held == "[CITE:chunk:"

    def test_partial_open_bracket(self) -> None:
        result = _split_incomplete_cite("text [")
        assert result is not None
        safe, held = result
        assert safe == "text "
        assert held == "["

    def test_partial_delim_prefix_held(self) -> None:
        result = _split_incomplete_cite("abc [CIT")
        assert result is not None
        safe, held = result
        assert safe == "abc "
        assert held == "[CIT"

    def test_complete_edge_cite_returns_none(self) -> None:
        assert _split_incomplete_cite("[CITE:edge:e1]") is None

    def test_complete_chunk_cite_returns_none(self) -> None:
        assert _split_incomplete_cite("[CITE:chunk:c1]") is None

    def test_complete_page_cite_returns_none(self) -> None:
        assert _split_incomplete_cite("[CITE:page:12]") is None


# ---------------------------------------------------------------------------
# Citation event dispatch
# ---------------------------------------------------------------------------


@pytest.fixture
def node_cache() -> dict[str, str]:
    return {"n1": "核心论点", "n2": "分论点"}


@pytest.fixture
def edge_cache() -> dict[str, str]:
    return {"e1": "分论点 → 核心论点", "e2": "历史制度主义 → 核心论点"}


@pytest.fixture
def chunk_cache() -> dict[str, str]:
    return {"c1": "制度一旦形成便会产生路径依赖。"}


class TestDispatchCitation:
    """Cover the four citation dispatch branches."""

    def test_node_citation_has_type_and_node_id(
        self, node_cache: dict[str, str], edge_cache: dict[str, str], chunk_cache: dict[str, str]
    ) -> None:
        evt = dispatch_citation("", "n1", "hss-001", node_cache, edge_cache, chunk_cache)
        assert evt.event == "citation"
        assert evt.data["type"] == "node"
        assert evt.data["paper_id"] == "hss-001"
        assert evt.data["node_id"] == "n1"
        assert evt.data["label"] == "核心论点"

    def test_edge_citation_has_type_and_edge_id(
        self, node_cache: dict[str, str], edge_cache: dict[str, str], chunk_cache: dict[str, str]
    ) -> None:
        evt = dispatch_citation("edge:", "e1", "hss-001", node_cache, edge_cache, chunk_cache)
        assert evt.event == "citation"
        assert evt.data["type"] == "edge"
        assert evt.data["paper_id"] == "hss-001"
        assert evt.data["edge_id"] == "e1"
        assert evt.data["label"] == "分论点 → 核心论点"

    def test_chunk_citation_has_type_and_text_preview(
        self, node_cache: dict[str, str], edge_cache: dict[str, str], chunk_cache: dict[str, str]
    ) -> None:
        evt = dispatch_citation("chunk:", "c1", "hss-001", node_cache, edge_cache, chunk_cache)
        assert evt.event == "citation"
        assert evt.data["type"] == "chunk"
        assert evt.data["paper_id"] == "hss-001"
        assert evt.data["chunk_id"] == "c1"
        assert "text_preview" in evt.data
        assert evt.data["text_preview"] == "制度一旦形成便会产生路径依赖。"
        assert evt.data["preview_state"] == "ready"

    def test_chunk_citation_miss_emits_structured_placeholder(
        self, node_cache: dict[str, str], edge_cache: dict[str, str], chunk_cache: dict[str, str]
    ) -> None:
        from backend.rag.chunk_preview import CHUNK_PREVIEW_HALLUCINATION
        from backend.schemas.chunk_preview import ChunkPreviewState

        evt = dispatch_citation("chunk:", "missing", "hss-001", node_cache, edge_cache, chunk_cache)
        assert evt.data["text_preview"] == CHUNK_PREVIEW_HALLUCINATION
        assert evt.data["preview_state"] == ChunkPreviewState.HALLUCINATED_ID
        assert evt.data["text_preview"] != ""

    def test_page_citation_has_type_and_page(
        self, node_cache: dict[str, str], edge_cache: dict[str, str], chunk_cache: dict[str, str]
    ) -> None:
        evt = dispatch_citation("page:", "12", "hss-001", node_cache, edge_cache, chunk_cache)
        assert evt.event == "citation"
        assert evt.data["type"] == "page"
        assert evt.data["paper_id"] == "hss-001"
        assert evt.data["page"] == 12
        assert "第12页" in evt.data["label"]

    def test_page_non_integer_treated_as_string(
        self, node_cache: dict[str, str], edge_cache: dict[str, str], chunk_cache: dict[str, str]
    ) -> None:
        evt = dispatch_citation("page:", "appendix", "hss-001", node_cache, edge_cache, chunk_cache)
        assert evt.data["type"] == "page"
        assert evt.data["page"] == "appendix"

    def test_unknown_node_id_falls_back_to_raw_id(
        self, node_cache: dict[str, str], edge_cache: dict[str, str], chunk_cache: dict[str, str]
    ) -> None:
        evt = dispatch_citation("", "n_missing", "hss-001", node_cache, edge_cache, chunk_cache)
        assert evt.data["type"] == "node"
        assert evt.data["node_id"] == "n_missing"
        assert evt.data["label"] == "n_missing"


# ---------------------------------------------------------------------------
# Edge label cache
# ---------------------------------------------------------------------------


class TestBuildEdgeLabelCache:
    """Edge label auto-joining from source/target nodes."""

    def test_returns_empty_for_empty_edges(self) -> None:
        graph = UnifiedPaperGraph(
            paper_id="p1",
            paradigm=Paradigm.HSS,
            nodes=[GraphNode(id="n1", label="Thesis", type="Thesis")],
            edges=[],
        )
        cache = _build_edge_label_cache(graph)
        assert cache == {}

    def test_joins_source_target_labels(self) -> None:
        graph = UnifiedPaperGraph(
            paper_id="p1",
            paradigm=Paradigm.HSS,
            nodes=[
                GraphNode(id="n1", label="核心论点", type="Thesis"),
                GraphNode(id="n2", label="分论点", type="SubArgument"),
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
        cache = _build_edge_label_cache(graph)
        assert cache["e1"] == "分论点 → 核心论点"

    def test_multiple_edges_are_all_cached(self) -> None:
        graph = UnifiedPaperGraph(
            paper_id="p1",
            paradigm=Paradigm.HSS,
            nodes=[
                GraphNode(id="n1", label="Thesis", type="Thesis"),
                GraphNode(id="n2", label="Sub", type="SubArgument"),
                GraphNode(id="n3", label="Lens", type="AnalyticalLens"),
            ],
            edges=[
                GraphEdge(
                    id="e1",
                    source="n2",
                    target="n1",
                    label="S",
                    type="SUB_ARGUMENT_OF",
                ),
                GraphEdge(
                    id="e2",
                    source="n3",
                    target="n1",
                    label="L",
                    type="LENS_OF",
                ),
            ],
        )
        cache = _build_edge_label_cache(graph)
        assert len(cache) == 2
        assert cache["e1"] == "Sub → Thesis"
        assert cache["e2"] == "Lens → Thesis"

    def test_cache_resilient_to_extra_nodes(self) -> None:
        """Only edges present in the graph produce cache entries."""
        graph = UnifiedPaperGraph(
            paper_id="p1",
            paradigm=Paradigm.HSS,
            nodes=[
                GraphNode(id="n1", label="A", type="Thesis"),
                GraphNode(id="n2", label="B", type="SubArgument"),
                GraphNode(id="n3", label="C", type="AnalyticalLens"),
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
        cache = _build_edge_label_cache(graph)
        assert len(cache) == 1
        assert cache["e1"] == "B → A"


# ---------------------------------------------------------------------------
# Chunk text cache
# ---------------------------------------------------------------------------


class TestBuildChunkTextCache:
    def test_returns_empty_for_none(self) -> None:
        assert build_chunk_text_cache(None) == {}

    def test_returns_empty_for_empty_list(self) -> None:
        assert build_chunk_text_cache([]) == {}

    def test_maps_chunk_ids_to_text(self) -> None:
        chunks = [
            RetrievedChunk(
                id="rc-c1",
                paper_id="p1",
                text="Text chunk one.",
                chunk_id="c1",
                chunk_index=1,
                char_start=0,
                char_end=14,
                distance=0.12,
            ),
            RetrievedChunk(
                id="rc-c2",
                paper_id="p1",
                text="Text chunk two.",
                chunk_id="c2",
                chunk_index=2,
                char_start=15,
                char_end=29,
                distance=0.34,
            ),
        ]
        cache = build_chunk_text_cache(chunks)
        assert cache == {"c1": "Text chunk one.", "c2": "Text chunk two."}


# ---------------------------------------------------------------------------
# RetrievalContext formatting
# ---------------------------------------------------------------------------


def _make_chunk(
    chunk_id: str,
    text: str,
    *,
    page_start: int | None = None,
    distance: float = 0.1,
    section: str | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        id=f"rc-{chunk_id}",
        paper_id="p1",
        text=text,
        chunk_id=chunk_id,
        chunk_index=int(chunk_id.lstrip("c") or 0),
        char_start=0,
        char_end=len(text),
        distance=distance,
        page_start=page_start,
        page_end=page_start,
        section=section,
    )


def _make_entity(
    entity_id: str,
    *,
    label: str = "L",
    node_type: str = "T",
    distance: float = 0.1,
) -> RetrievedEntity:
    return RetrievedEntity(
        id=f"re-{entity_id}",
        paper_id="p1",
        text=f"{label} desc",
        entity_id=entity_id,
        label=label,
        node_type=node_type,
        distance=distance,
    )


def _make_relation(
    relation_id: str,
    *,
    description: str = "rel desc",
    source_id: str = "n_src",
    target_id: str = "n_tgt",
    relation_type: str = "RELATES_TO",
    distance: float = 0.1,
) -> RetrievedRelation:
    return RetrievedRelation(
        id=f"rr-{relation_id}",
        paper_id="p1",
        text=description,
        relation_id=relation_id,
        source_id=source_id,
        target_id=target_id,
        relation_type=relation_type,
        distance=distance,
    )


class TestFormatRetrievalContext:
    """V2 prompt-section generation from RetrievalContext."""

    def test_none_returns_three_empty_strings(self) -> None:
        entities, relations, chunks = format_retrieval_context(None)
        assert entities == ""
        assert relations == ""
        assert chunks == ""

    def test_empty_context_returns_placeholders(self) -> None:
        rc = RetrievalContext(scale=QuestionScale.DETAIL)
        entities, relations, chunks = format_retrieval_context(rc)
        assert "暂无向量召回实体" in entities
        assert "暂无向量召回关系" in relations
        assert "向量索引尚未就绪" in chunks

    def test_entities_formatted_with_label_and_type(self) -> None:
        rc = RetrievalContext(
            scale=QuestionScale.DETAIL,
            entities=[_make_entity("n1", label="核心论点", node_type="Thesis")],
        )
        entities, _, _ = format_retrieval_context(rc)
        assert "核心论点" in entities
        assert "Thesis" in entities
        assert "n1" in entities

    def test_relations_formatted_with_description(self) -> None:
        rc = RetrievalContext(
            scale=QuestionScale.DETAIL,
            relations=[
                _make_relation("e1", description="分论点支撑核心论点。"),
            ],
        )
        _, relations, _ = format_retrieval_context(rc)
        assert "分论点支撑核心论点" in relations
        assert "e1" in relations

    def test_chunks_formatted_with_page_info(self) -> None:
        rc = RetrievalContext(
            scale=QuestionScale.DETAIL,
            chunks=[
                _make_chunk("c1", "Institution text.", page_start=3),
                _make_chunk("c2", "Another chunk.", section="methods"),
            ],
        )
        _, _, chunks = format_retrieval_context(rc)
        assert "[page 3]" in chunks
        assert "Institution text" in chunks
        assert "Another chunk" in chunks

    def test_all_three_sections_together(self) -> None:
        rc = RetrievalContext(
            scale=QuestionScale.DETAIL,
            entities=[_make_entity("n1", label="L1", node_type="T1")],
            relations=[_make_relation("e1", description="rel desc")],
            chunks=[_make_chunk("c1", "chunk text")],
        )
        entities, relations, chunks = format_retrieval_context(rc)
        assert entities != ""
        assert relations != ""
        assert chunks != ""
        assert "L1" in entities
        assert "rel desc" in relations
        assert "chunk text" in chunks

    def test_context_char_budget_truncates_chunks_first(self) -> None:
        rc = RetrievalContext(
            scale=QuestionScale.DETAIL,
            entities=[_make_entity("n1", label="核心论点")],
            relations=[_make_relation("e1", description="关系描述")],
            chunks=[
                _make_chunk("c1", "A" * 400),
                _make_chunk("c2", "B" * 400),
                _make_chunk("c3", "C" * 400),
            ],
        )
        entities, relations, chunks = format_retrieval_context(rc, max_total_chars=600)
        total = len(entities) + len(relations) + len(chunks)
        assert total <= 600
        assert "检索上下文已截断" in chunks
        assert "核心论点" in entities
        assert "关系描述" in relations

    def test_context_char_budget_preserves_small_context(self) -> None:
        rc = RetrievalContext(
            scale=QuestionScale.DETAIL,
            chunks=[_make_chunk("c1", "short chunk")],
        )
        entities, relations, chunks = format_retrieval_context(rc, max_total_chars=12_000)
        assert "short chunk" in chunks
        assert "检索上下文已截断" not in chunks
