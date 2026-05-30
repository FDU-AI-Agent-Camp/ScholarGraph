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


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


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
def store_with_graph(tmp_path: Path, hss_graph: UnifiedPaperGraph) -> GraphStore:
    """GraphStore that already contains *hss_graph*."""
    s = GraphStore(base_dir=tmp_path)
    s.save(hss_graph)
    return s


@pytest.fixture
def empty_store(tmp_path: Path) -> GraphStore:
    return GraphStore(base_dir=tmp_path)


# ---------------------------------------------------------------------------
# event type smoke tests
# ---------------------------------------------------------------------------


class TestQaStreamEvents:
    async def test_yields_message_events_when_llm_responds(
        self, store_with_graph: GraphStore
    ) -> None:
        llm = _fake_llm("这是一篇关于数字劳动的论文。")
        engine = _GraphQaEngine(store=store_with_graph, llm=llm)

        events = [
            evt
            async for evt in engine.stream("hss-001", "这篇论文做了什么？")
        ]
        message_events = [e for e in events if e.event == "message"]
        assert len(message_events) >= 1

    async def test_yields_citation_event_for_marker(
        self, store_with_graph: GraphStore
    ) -> None:
        llm = _fake_llm("本文核心论点[CITE:n1]涉及社会不平等。")
        engine = _GraphQaEngine(store=store_with_graph, llm=llm)

        events = [
            evt
            async for evt in engine.stream("hss-001", "核心论点是什么？")
        ]
        citation_events = [e for e in events if e.event == "citation"]
        assert len(citation_events) >= 1
        cite = citation_events[0]
        assert cite.data["node_id"] == "n1"
        assert cite.data["paper_id"] == "hss-001"
        assert "核心论点" in cite.data["label"]

    async def test_yields_done_event(self, store_with_graph: GraphStore) -> None:
        llm = _fake_llm("test")
        engine = _GraphQaEngine(store=store_with_graph, llm=llm)

        events = [
            evt
            async for evt in engine.stream("hss-001", "question")
        ]
        done_events = [e for e in events if e.event == "done"]
        assert len(done_events) == 1
        assert done_events[0].data["answer_id"].startswith("ans-")

    async def test_last_event_is_done(self, store_with_graph: GraphStore) -> None:
        llm = _fake_llm("test")
        engine = _GraphQaEngine(store=store_with_graph, llm=llm)

        events = [
            evt
            async for evt in engine.stream("hss-001", "question")
        ]
        assert events[-1].event == "done"


# ---------------------------------------------------------------------------
# error paths
# ---------------------------------------------------------------------------


class TestQaStreamErrors:
    async def test_missing_graph_yields_error_then_done(
        self, empty_store: GraphStore
    ) -> None:
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
