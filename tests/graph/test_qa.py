# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Tests for qa_stream (BE-3).

Uses fake LLM objects to avoid real API calls.  Tests cover all four SSE
event types as well as error paths.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from backend.graph.qa import QaEvent, _GraphQaEngine
from backend.graph.store import GraphStore
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm

from tests.helpers.persistence_testkit import seed_qa_graph_with_db

# ---------------------------------------------------------------------------
# fake LLM harness — real async generators, not mocks
# ---------------------------------------------------------------------------


class _FakeChunk:
    """Minimal stand-in for a LangChain AIMessageChunk."""

    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChat:
    """Fake ``.chat`` whose ``astream(prompt)`` is a genuine async generator."""

    def __init__(self, text: str, chunk_size: int = 5) -> None:
        self._text = text
        self._chunk_size = chunk_size

    async def astream(self, _prompt: str) -> AsyncIterator[_FakeChunk]:
        for i in range(0, len(self._text), self._chunk_size):
            yield _FakeChunk(self._text[i : i + self._chunk_size])


def _fake_llm(text: str, chunk_size: int = 5) -> object:
    """Return an object whose ``.chat.astream(prompt)`` yields fake chunks."""
    obj = type("FakeLlmClient", (), {})()
    obj.chat = _FakeChat(text, chunk_size)
    return obj


def _bad_llm() -> object:
    """Return an object whose ``.chat.astream(prompt)`` always raises."""

    async def _raise(_self, _prompt: str) -> AsyncIterator[None]:  # noqa: ARG001
        raise RuntimeError("LLM connection refused")
        yield  # unreachable — makes this an async generator

    obj = type("BadLlmClient", (), {})()
    obj.chat = type("BadChat", (), {"astream": _raise})()
    return obj


@pytest.fixture
def hss_graph() -> UnifiedPaperGraph:
    return UnifiedPaperGraph(
        paper_id="hss-001",
        paradigm=Paradigm.HSS,
        nodes=[
            GraphNode(id="n1", label="核心论点：社会不平等加剧", type="Thesis"),
            GraphNode(id="n2", label="分论点1：平台算法强化劳动控制", type="SubArgument"),
        ],
        edges=[
            GraphEdge(id="e1", source="n2", target="n1", label="SUB_ARGUMENT_OF", type="SUB_ARGUMENT_OF"),
        ],
    )


@pytest.fixture
def store_with_graph(tmp_path: Path, hss_graph: UnifiedPaperGraph, monkeypatch: pytest.MonkeyPatch) -> GraphStore:
    """GraphStore that already contains *hss_graph* and a matching READY paper row."""
    return seed_qa_graph_with_db(tmp_path, monkeypatch, hss_graph)


@pytest.fixture
def empty_store(tmp_path: Path) -> GraphStore:
    return GraphStore(base_dir=tmp_path)


# ---------------------------------------------------------------------------
# event type smoke tests
# ---------------------------------------------------------------------------


class TestQaStreamEvents:
    async def test_yields_message_events_when_llm_responds(self, store_with_graph: GraphStore) -> None:
        llm = _fake_llm("这是一篇关于数字劳动的论文。")
        engine = _GraphQaEngine(store=store_with_graph, llm=llm)

        events = [evt async for evt in engine.stream("hss-001", "这篇论文做了什么？")]
        message_events = [e for e in events if e.event == "message"]
        assert len(message_events) >= 1

    async def test_yields_citation_event_for_marker(self, store_with_graph: GraphStore) -> None:
        llm = _fake_llm("本文核心论点[CITE:n1]涉及社会不平等。")
        engine = _GraphQaEngine(store=store_with_graph, llm=llm)

        events = [evt async for evt in engine.stream("hss-001", "核心论点是什么？")]
        citation_events = [e for e in events if e.event == "citation"]
        assert len(citation_events) >= 1
        cite = citation_events[0]
        assert cite.data["node_id"] == "n1"
        assert cite.data["paper_id"] == "hss-001"
        assert "核心论点" in cite.data["label"]

    async def test_yields_citation_when_marker_splits_across_chunks(
        self,
        store_with_graph: GraphStore,
    ) -> None:
        llm = _fake_llm("参见节点[CITE:n_lens]完成验证。", chunk_size=8)
        engine = _GraphQaEngine(store=store_with_graph, llm=llm)

        events = [evt async for evt in engine.stream("hss-001", "验证")]
        citation_events = [e for e in events if e.event == "citation"]
        assert len(citation_events) == 1
        assert citation_events[0].data["node_id"] == "n_lens"

    async def test_yields_done_event(self, store_with_graph: GraphStore) -> None:
        llm = _fake_llm("test")
        engine = _GraphQaEngine(store=store_with_graph, llm=llm)

        events = [evt async for evt in engine.stream("hss-001", "question")]
        done_events = [e for e in events if e.event == "done"]
        assert len(done_events) == 1
        assert done_events[0].data["answer_id"].startswith("ans-")

    async def test_last_event_is_done(self, store_with_graph: GraphStore) -> None:
        llm = _fake_llm("test")
        engine = _GraphQaEngine(store=store_with_graph, llm=llm)

        events = [evt async for evt in engine.stream("hss-001", "question")]
        assert events[-1].event == "done"


# ---------------------------------------------------------------------------
# Markdown artifact sanitization
# ---------------------------------------------------------------------------


class TestQaStreamMarkdownSanitization:
    async def test_strips_empty_backticks_from_message(self, store_with_graph: GraphStore) -> None:
        llm = _fake_llm("问题``。")
        engine = _GraphQaEngine(store=store_with_graph, llm=llm)

        events = [evt async for evt in engine.stream("hss-001", "问题？")]
        messages = "".join(evt.data["delta"] for evt in events if evt.event == "message")
        assert "`" not in messages
        assert messages == "问题。"

    async def test_strips_inline_code_span(self, store_with_graph: GraphStore) -> None:
        llm = _fake_llm("方法`RAG-Sequence`有效。")
        engine = _GraphQaEngine(store=store_with_graph, llm=llm)

        events = [evt async for evt in engine.stream("hss-001", "方法？")]
        messages = "".join(evt.data["delta"] for evt in events if evt.event == "message")
        assert "`" not in messages
        assert "RAG-Sequence" in messages

    async def test_citation_inside_backticks_still_emits_citation(
        self,
        store_with_graph: GraphStore,
    ) -> None:
        llm = _fake_llm("方案`[CITE:n1]`说明。")
        engine = _GraphQaEngine(store=store_with_graph, llm=llm)

        events = [evt async for evt in engine.stream("hss-001", "方案？")]
        citation_events = [e for e in events if e.event == "citation"]
        messages = "".join(evt.data["delta"] for evt in events if evt.event == "message")
        assert len(citation_events) == 1
        assert citation_events[0].data["node_id"] == "n1"
        assert "`" not in messages
        assert "方案" in messages

    async def test_empty_backticks_survive_chunked_stream(self, store_with_graph: GraphStore) -> None:
        llm = _fake_llm("问题``。", chunk_size=2)
        engine = _GraphQaEngine(store=store_with_graph, llm=llm)

        events = [evt async for evt in engine.stream("hss-001", "问题？")]
        messages = "".join(evt.data["delta"] for evt in events if evt.event == "message")
        done = next(evt for evt in events if evt.event == "done")
        assert "`" not in messages
        assert messages == "问题。"
        assert done.data.get("answer") == "问题。"


# ---------------------------------------------------------------------------
# V2 citation types (rag-qa-evaluation)
# ---------------------------------------------------------------------------


class TestQaStreamV2Citations:
    """Cover edge, chunk, and page citation SSE events."""

    async def test_yields_edge_citation_with_joined_label(
        self,
        store_with_graph: GraphStore,
    ) -> None:
        llm = _fake_llm("关系[CITE:edge:e1]连接了两个节点。")
        engine = _GraphQaEngine(store=store_with_graph, llm=llm)

        events = [evt async for evt in engine.stream("hss-001", "关系是什么？")]
        citation_events = [e for e in events if e.event == "citation"]
        assert len(citation_events) >= 1
        cite = citation_events[0]
        assert cite.data["type"] == "edge"
        assert cite.data["edge_id"] == "e1"
        assert cite.data["paper_id"] == "hss-001"
        # label should be auto-joined from source -> target
        assert "→" in cite.data["label"]

    async def test_yields_chunk_citation_with_text_preview(
        self,
        store_with_graph: GraphStore,
    ) -> None:
        llm = _fake_llm("原文[CITE:chunk:c1]中有详细描述。")
        engine = _GraphQaEngine(store=store_with_graph, llm=llm)

        events = [evt async for evt in engine.stream("hss-001", "原文内容？")]
        citation_events = [e for e in events if e.event == "citation"]
        assert len(citation_events) >= 1
        cite = citation_events[0]
        assert cite.data["type"] == "chunk"
        assert cite.data["chunk_id"] == "c1"
        assert cite.data["paper_id"] == "hss-001"

    async def test_yields_page_citation_with_page_number(
        self,
        store_with_graph: GraphStore,
    ) -> None:
        llm = _fake_llm("参看[CITE:page:12]的论述。")
        engine = _GraphQaEngine(store=store_with_graph, llm=llm)

        events = [evt async for evt in engine.stream("hss-001", "第几页？")]
        citation_events = [e for e in events if e.event == "citation"]
        assert len(citation_events) >= 1
        cite = citation_events[0]
        assert cite.data["type"] == "page"
        assert cite.data["page"] == 12
        assert cite.data["paper_id"] == "hss-001"

    async def test_node_citation_has_type_node_attached(self, store_with_graph: GraphStore) -> None:
        """V1 backward-compat: bare [CITE:n1] gets type=node with node_id."""
        llm = _fake_llm("核心论点[CITE:n1]是关键。")
        engine = _GraphQaEngine(store=store_with_graph, llm=llm)

        events = [evt async for evt in engine.stream("hss-001", "test")]
        citation_events = [e for e in events if e.event == "citation"]
        assert len(citation_events) >= 1
        cite = citation_events[0]
        assert cite.data["type"] == "node"
        assert cite.data["node_id"] == "n1"

    async def test_mixed_citations_in_one_stream(self, store_with_graph: GraphStore) -> None:
        llm = _fake_llm("论点[CITE:n1]由关系[CITE:edge:e1]连接，原文[CITE:chunk:c1]有详述，见[CITE:page:5]。")
        engine = _GraphQaEngine(store=store_with_graph, llm=llm)

        events = [evt async for evt in engine.stream("hss-001", "test")]
        citation_events = [e for e in events if e.event == "citation"]
        types = {c.data["type"] for c in citation_events}
        assert "node" in types
        assert "edge" in types
        assert "chunk" in types
        assert "page" in types


# ---------------------------------------------------------------------------
# boundary handling (§4 checklist)
# ---------------------------------------------------------------------------


class TestQaStreamBoundaryHandling:
    async def test_empty_retrieval_context_completes_without_error(
        self,
        store_with_graph: GraphStore,
    ) -> None:
        """Blank vector index: RC.chunks=[] must not raise IndexError; graph citations still work."""
        from backend.rag.models import QuestionScale, RetrievalContext

        rc = RetrievalContext(scale=QuestionScale.DETAIL)
        llm = _fake_llm("依据图谱，核心论点[CITE:n1]说明问题。")
        engine = _GraphQaEngine(store=store_with_graph, llm=llm)

        events = [
            evt
            async for evt in engine.stream(
                "hss-001",
                "分论点如何支撑核心论点？",
                retrieval_context=rc,
            )
        ]
        assert not any(evt.event == "error" for evt in events)
        assert events[-1].event == "done"
        node_citations = [evt for evt in events if evt.event == "citation" and evt.data.get("type") == "node"]
        assert len(node_citations) >= 1


# ---------------------------------------------------------------------------
# error paths
# ---------------------------------------------------------------------------


class TestQaStreamErrors:
    async def test_missing_graph_yields_error_then_done(self, empty_store: GraphStore) -> None:
        engine = _GraphQaEngine(store=empty_store, llm=_fake_llm(""))
        events = [evt async for evt in engine.stream("no-such-id", "question")]

        error_events = [e for e in events if e.event == "error"]
        done_events = [e for e in events if e.event == "done"]
        assert len(error_events) == 1
        assert error_events[0].data["code"] == "GRAPH_NOT_FOUND"
        assert len(done_events) == 1

    async def test_llm_exception_yields_error(self, store_with_graph: GraphStore) -> None:
        engine = _GraphQaEngine(store=store_with_graph, llm=_bad_llm())

        events = [evt async for evt in engine.stream("hss-001", "question")]
        error_events = [e for e in events if e.event == "error"]
        assert len(error_events) == 1
        assert "LLM connection refused" in error_events[0].data["message"]


# ---------------------------------------------------------------------------
# QaEvent
# ---------------------------------------------------------------------------


class TestQaEvent:
    def test_repr(self) -> None:
        evt = QaEvent("message", {"delta": "hello"})
        assert "message" in repr(evt)
        assert "hello" in repr(evt)
