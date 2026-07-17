# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""B7 acceptance — RetrievalContext SSOT audit, fallback, and prompt consistency."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from unittest.mock import patch

import pytest
from backend.config import get_settings
from backend.graph.qa import qa_stream
from backend.graph.query import GraphQuery
from backend.graph.store import GraphStore
from backend.llm.client import reset_llm_client_cache
from backend.rag.hybrid_retriever import HybridRetriever
from backend.rag.models import QuestionScale, RetrievalContext
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm
from backend.services.paper_fixture_seed import seed_from_fixtures
from backend.services.paper_service import PaperService, get_paper_service
from backend.services.qa_service import QaService

from tests.graph.test_qa import _FakeChunk
from tests.helpers.persistence_testkit import run_async

MOCK_NODE_B7_LABEL = "MockNode_B7_Verify"
MOCK_NODE_B7_ID = "mock-node-b7"


class _CapturingFakeChat:
    """Records the full prompt text passed to the fake LLM."""

    def __init__(self, response: str = "回答[CITE:n1]。") -> None:
        self.prompt = ""
        self._response = response

    async def astream(self, prompt: str) -> AsyncIterator[_FakeChunk]:
        self.prompt = prompt
        yield _FakeChunk(self._response)


def _capturing_llm(response: str = "回答[CITE:n1]。") -> tuple[object, _CapturingFakeChat]:
    chat = _CapturingFakeChat(response)
    client = type("CapturingLlmClient", (), {})()
    client.chat = chat
    return client, chat


def _hss_graph() -> UnifiedPaperGraph:
    return UnifiedPaperGraph(
        paper_id="hss-001",
        paradigm=Paradigm.HSS,
        nodes=[
            GraphNode(id="n1", label="核心论点", type="Thesis", data={}),
            GraphNode(id="n2", label="分论点：制度路径依赖", type="SubArgument", data={}),
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


def _seed_graph_store(tmp_path: Path) -> GraphStore:
    store = GraphStore(base_dir=tmp_path)
    store.save(_hss_graph())
    return store


def _extract_prompt_section(prompt: str, heading: str) -> str:
    marker = f"### {heading}"
    start = prompt.find(marker)
    if start < 0:
        return ""
    rest = prompt[start + len(marker) :]
    end = rest.find("\n### ")
    if end < 0:
        end = rest.find("\n## ")
    return rest[:end] if end >= 0 else rest


class _SubgraphQuerySpy:
    """Call-count audit wrapper for ``GraphQuery.subgraph_for_question``."""

    def __init__(self) -> None:
        self.call_count = 0
        self._original = GraphQuery.subgraph_for_question
        spy = self

        def _wrapped(gq_self: GraphQuery, graph: UnifiedPaperGraph, question: str) -> dict:
            spy.call_count += 1
            return spy._original(gq_self, graph, question)

        self._patch = patch.object(
            GraphQuery,
            "subgraph_for_question",
            autospec=True,
            side_effect=_wrapped,
        )

    def __enter__(self) -> _SubgraphQuerySpy:
        self._patch.__enter__()
        return self

    def __exit__(self, *args: object) -> None:
        self._patch.__exit__(*args)


@pytest.fixture
def subgraph_query_spy() -> Callable[[], _SubgraphQuerySpy]:
    return _SubgraphQuerySpy


@pytest.fixture
def graph_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> GraphStore:
    """Isolated graph dir + paper fixture aligned with hss-001."""
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_dir))
    monkeypatch.setenv("LLM_MODE", "mock")
    get_settings.cache_clear()
    reset_llm_client_cache()
    return _seed_graph_store(graph_dir)


@pytest.fixture
def paper_service() -> PaperService:
    service = get_paper_service()
    run_async(seed_from_fixtures(service._paper_repo, service._pipeline_repo))
    return service


@pytest.mark.asyncio
async def test_subgraph_query_called_exactly_once_in_hybrid_rag_pipeline(
    graph_env: GraphStore,
    paper_service: PaperService,
    subgraph_query_spy: Callable[[], _SubgraphQuerySpy],
) -> None:
    """Audit: GraphQuery.subgraph_for_question runs once (HybridRetriever only)."""
    retriever = HybridRetriever(vector_store=None)
    llm, _chat = _capturing_llm()

    service = QaService(
        store=graph_env,
        paper_service=paper_service,
        hybrid_retriever=retriever,
    )

    with subgraph_query_spy() as spy:
        events = [
            evt
            async for evt in service.stream(
                "hss-001",
                "分论点如何支撑核心论点？",
                llm=llm,
            )
        ]

    assert not any(evt.event == "error" for evt in events)
    assert events[-1].event == "done"
    assert spy.call_count == 1, "GraphQuery must run exactly once — no QaEngine double-fetch"


@pytest.mark.asyncio
async def test_qa_stream_none_context_falls_back_without_attribute_error(
    graph_env: GraphStore,
    subgraph_query_spy: Callable[[], _SubgraphQuerySpy],
) -> None:
    """V1 path: retrieval_context=None triggers lazy GraphQuery fallback (call_count=1)."""
    llm, chat = _capturing_llm()

    with subgraph_query_spy() as spy:
        events = [
            evt
            async for evt in qa_stream(
                "hss-001",
                "这篇论文的核心论点是什么？",
                retrieval_context=None,
                llm=llm,
            )
        ]

    assert not any(evt.event == "error" for evt in events)
    assert events[-1].event == "done"
    assert spy.call_count == 1
    assert "[n1]" in chat.prompt


@pytest.mark.asyncio
async def test_prompt_nodes_section_renders_retrieval_context_subgraph(
    graph_env: GraphStore,
    subgraph_query_spy: Callable[[], _SubgraphQuerySpy],
) -> None:
    """Prompt {nodes} must reflect RC.nodes when RC also carries edges (complete subgraph)."""
    rc = RetrievalContext(
        scale=QuestionScale.DETAIL,
        nodes=[
            {
                "id": MOCK_NODE_B7_ID,
                "label": MOCK_NODE_B7_LABEL,
                "type": "Thesis",
            },
        ],
        edges=[
            {
                "source": MOCK_NODE_B7_ID,
                "target": "n1",
                "label": "MOCK_EDGE_B7",
            },
        ],
    )
    llm, chat = _capturing_llm(f"依据图谱[CITE:{MOCK_NODE_B7_ID}]。")

    with subgraph_query_spy() as spy:
        events = [
            evt
            async for evt in qa_stream(
                "hss-001",
                "B7 prompt consistency check",
                retrieval_context=rc,
                llm=llm,
            )
        ]

    assert not any(evt.event == "error" for evt in events)
    assert spy.call_count == 0, "Complete RC subgraph must skip GraphQuery entirely"

    nodes_section = _extract_prompt_section(chat.prompt, "节点")
    assert MOCK_NODE_B7_LABEL in nodes_section
    assert f"[{MOCK_NODE_B7_ID}]" in nodes_section
    assert MOCK_NODE_B7_LABEL in chat.prompt


@pytest.mark.asyncio
async def test_partial_context_nodes_without_edges_triggers_edges_fallback(
    graph_env: GraphStore,
    subgraph_query_spy: Callable[[], _SubgraphQuerySpy],
) -> None:
    """Half-loaded RC (nodes present, edges=[]): reuse nodes, backfill edges only."""
    rc = RetrievalContext(
        scale=QuestionScale.DETAIL,
        nodes=[
            {
                "id": MOCK_NODE_B7_ID,
                "label": MOCK_NODE_B7_LABEL,
                "type": "Thesis",
            },
        ],
        edges=[],
    )
    llm, chat = _capturing_llm(f"依据图谱[CITE:{MOCK_NODE_B7_ID}]。")

    with subgraph_query_spy() as spy:
        events = [
            evt
            async for evt in qa_stream(
                "hss-001",
                "分论点如何支撑核心论点？",
                retrieval_context=rc,
                llm=llm,
            )
        ]

    assert not any(evt.event == "error" for evt in events)
    assert events[-1].event == "done"
    assert spy.call_count == 1, "Partial RC must trigger exactly one GraphQuery for edge backfill"

    nodes_section = _extract_prompt_section(chat.prompt, "节点")
    edges_section = _extract_prompt_section(chat.prompt, "关系")
    assert MOCK_NODE_B7_LABEL in nodes_section
    assert f"[{MOCK_NODE_B7_ID}]" in nodes_section
    assert "SUB_ARGUMENT_OF" in edges_section
    assert "n2" in edges_section and "n1" in edges_section


class _SlowCapturingFakeChat:
    """Yields multiple chunks with yields so concurrent mutators can run mid-stream."""

    def __init__(self, response: str = "回答[CITE:n1]。") -> None:
        self.prompt = ""
        self._response = response

    async def astream(self, prompt: str) -> AsyncIterator[_FakeChunk]:
        self.prompt = prompt
        for index in range(0, len(self._response), 3):
            yield _FakeChunk(self._response[index : index + 3])
            await asyncio.sleep(0.005)


async def _rc_destroyer_loop(rc: RetrievalContext, stop: asyncio.Event) -> None:
    """Simulate rogue async consumers mutating shared RC references."""
    while not stop.is_set():
        try:
            rc.nodes.clear()
            rc.edges.clear()
            rc.nodes.append({"id": "evil", "label": "MUTATED_BY_DESTROYER", "type": "Thesis"})
        except (AttributeError, RuntimeError):
            pass
        if rc.nodes:
            rc.nodes[0]["label"] = "MUTATED_BY_DESTROYER"
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_retrieval_context_immutable_under_async_stream_mutation(
    graph_env: GraphStore,
) -> None:
    """Engine deep-snapshot must survive concurrent .clear() / in-place dict edits."""
    rc = RetrievalContext(
        scale=QuestionScale.DETAIL,
        nodes=[
            {
                "id": MOCK_NODE_B7_ID,
                "label": MOCK_NODE_B7_LABEL,
                "type": "Thesis",
            },
        ],
        edges=[
            {
                "source": MOCK_NODE_B7_ID,
                "target": "n1",
                "label": "MOCK_EDGE_B7",
            },
        ],
    )
    llm_client = type("SlowCapturingLlmClient", (), {})()
    chat = _SlowCapturingFakeChat(f"依据图谱[CITE:{MOCK_NODE_B7_ID}]。")
    llm_client.chat = chat

    stop = asyncio.Event()
    destroyer = asyncio.create_task(_rc_destroyer_loop(rc, stop))
    try:
        events = [
            evt
            async for evt in qa_stream(
                "hss-001",
                "B7 immutability stress test",
                retrieval_context=rc,
                llm=llm_client,
            )
        ]
    finally:
        stop.set()
        await destroyer

    assert not any(evt.event == "error" for evt in events)
    assert events[-1].event == "done"
    assert MOCK_NODE_B7_LABEL in chat.prompt
    assert "MUTATED_BY_DESTROYER" not in chat.prompt
    assert "MOCK_EDGE_B7" in chat.prompt


@pytest.mark.asyncio
async def test_engine_stream_snapshots_retrieval_context_at_entry(
    graph_env: GraphStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify QaEngine applies freeze_retrieval_context before prompt assembly."""
    import backend.graph.qa as qa_module

    rc = RetrievalContext(
        scale=QuestionScale.DETAIL,
        nodes=[{"id": MOCK_NODE_B7_ID, "label": MOCK_NODE_B7_LABEL, "type": "Thesis"}],
        edges=[{"source": MOCK_NODE_B7_ID, "target": "n1", "label": "MOCK_EDGE_B7"}],
    )
    snapshots: list[tuple[RetrievalContext, RetrievalContext]] = []
    original_freeze = qa_module.freeze_retrieval_context

    def _tracking_freeze(candidate: RetrievalContext) -> RetrievalContext:
        frozen = original_freeze(candidate)
        snapshots.append((candidate, frozen))
        return frozen

    monkeypatch.setattr(qa_module, "freeze_retrieval_context", _tracking_freeze)

    llm, _chat = _capturing_llm()
    events = [
        evt
        async for evt in qa_stream(
            "hss-001",
            "snapshot audit",
            retrieval_context=rc,
            llm=llm,
        )
    ]

    assert not any(evt.event == "error" for evt in events)
    assert len(snapshots) == 1
    passed_in, frozen = snapshots[0]
    assert passed_in is rc
    assert frozen is not rc
    assert frozen.nodes is not rc.nodes
