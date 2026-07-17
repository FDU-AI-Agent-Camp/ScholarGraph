# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""B7 — RetrievalContext as single source of truth for QA prompt subgraph."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from backend.graph.qa import _GraphQaEngine
from backend.graph.qa_v2 import freeze_retrieval_context, resolve_prompt_subgraph
from backend.graph.store import GraphStore
from backend.rag.models import QuestionScale, RetrievalContext
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm

from tests.graph.test_qa import _FakeChunk
from tests.helpers.persistence_testkit import seed_qa_graph_with_db


class _CapturingFakeChat:
    """Records the prompt passed to the fake LLM."""

    def __init__(self, response: str = "ok") -> None:
        self.prompt = ""
        self._response = response

    async def astream(self, prompt: str) -> AsyncIterator[_FakeChunk]:
        self.prompt = prompt
        yield _FakeChunk(self._response)


def _capturing_llm(response: str = "ok") -> tuple[object, _CapturingFakeChat]:
    chat = _CapturingFakeChat(response)
    obj = type("CapturingLlmClient", (), {})()
    obj.chat = chat
    return obj, chat


@pytest.fixture
def hss_graph() -> UnifiedPaperGraph:
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


@pytest.fixture
def store_with_graph(tmp_path: Path, hss_graph: UnifiedPaperGraph, monkeypatch: pytest.MonkeyPatch) -> GraphStore:
    return seed_qa_graph_with_db(tmp_path, monkeypatch, hss_graph, graph_dir=tmp_path / "graphs")


def test_resolve_prompt_subgraph_prefers_retrieval_context() -> None:
    graph_query = MagicMock()
    rc = RetrievalContext(
        scale=QuestionScale.DETAIL,
        nodes=[{"id": "rc-n1", "label": "From RC", "type": "Thesis"}],
        edges=[{"source": "rc-n2", "target": "rc-n1", "label": "LENS_OF"}],
    )
    graph = MagicMock()

    subgraph = resolve_prompt_subgraph(graph, "question", rc, graph_query=graph_query)

    assert subgraph["nodes"][0]["id"] == "rc-n1"
    assert subgraph["edges"][0]["label"] == "LENS_OF"
    graph_query.subgraph_for_question.assert_not_called()


def test_freeze_retrieval_context_deep_copies_nested_fields() -> None:
    """Snapshot must isolate list containers and nested dict payloads."""
    rc = RetrievalContext(
        scale=QuestionScale.DETAIL,
        nodes=[{"id": "rc-n1", "label": "Immutable node", "type": "Thesis"}],
        edges=[{"source": "rc-n1", "target": "rc-n2", "label": "KEPT_EDGE"}],
    )
    frozen = freeze_retrieval_context(rc)

    rc.nodes[0]["label"] = "CORRUPTED"
    rc.nodes.clear()
    rc.edges.clear()

    assert frozen.nodes[0]["label"] == "Immutable node"
    assert frozen.edges[0]["label"] == "KEPT_EDGE"
    assert frozen is not rc
    assert frozen.nodes is not rc.nodes
    assert frozen.edges is not rc.edges


def test_resolve_prompt_subgraph_falls_back_when_rc_subgraph_empty() -> None:
    graph_query = MagicMock()
    graph_query.subgraph_for_question.return_value = {
        "nodes": [{"id": "n1", "label": "核心论点", "type": "Thesis"}],
        "edges": [],
    }
    rc = RetrievalContext(scale=QuestionScale.DETAIL)
    graph = MagicMock()

    subgraph = resolve_prompt_subgraph(graph, "question", rc, graph_query=graph_query)

    assert subgraph["nodes"][0]["id"] == "n1"
    graph_query.subgraph_for_question.assert_called_once_with(graph, "question")


def test_resolve_prompt_subgraph_partial_edges_fallback_reuses_rc_nodes() -> None:
    """Nodes-only RC: backfill edges via GraphQuery without discarding RC nodes."""
    graph_query = MagicMock()
    graph_query.subgraph_for_question.return_value = {
        "nodes": [{"id": "gq-n1", "label": "GraphQuery node", "type": "Thesis"}],
        "edges": [{"source": "n2", "target": "n1", "label": "SUB_ARGUMENT_OF"}],
    }
    rc = RetrievalContext(
        scale=QuestionScale.DETAIL,
        nodes=[{"id": "rc-n1", "label": "RC node kept", "type": "Thesis"}],
        edges=[],
    )
    graph = MagicMock()

    subgraph = resolve_prompt_subgraph(graph, "question", rc, graph_query=graph_query)

    assert subgraph["nodes"][0]["id"] == "rc-n1"
    assert subgraph["edges"][0]["label"] == "SUB_ARGUMENT_OF"
    graph_query.subgraph_for_question.assert_called_once_with(graph, "question")


@pytest.mark.asyncio
async def test_qa_stream_prompt_nodes_match_rc_without_second_graph_query(
    store_with_graph: GraphStore,
) -> None:
    """Partial RC (nodes only): RC nodes preserved; GraphQuery runs once for edges."""
    rc_nodes = [{"id": "rc-only", "label": "RC 权威节点", "type": "Thesis"}]
    rc = RetrievalContext(scale=QuestionScale.DETAIL, nodes=rc_nodes, edges=[])

    graph_query = MagicMock()
    graph_query.subgraph_for_question.return_value = {
        "nodes": [{"id": "n1", "label": "核心论点", "type": "Thesis"}],
        "edges": [{"source": "n2", "target": "n1", "label": "SUB_ARGUMENT_OF"}],
    }

    llm, chat = _capturing_llm("回答[CITE:rc-only]。")
    engine = _GraphQaEngine(store=store_with_graph, llm=llm, query=graph_query)

    events = [
        evt
        async for evt in engine.stream(
            "hss-001",
            "分论点如何支撑核心论点？",
            retrieval_context=rc,
        )
    ]

    assert not any(evt.event == "error" for evt in events)
    assert "[rc-only]" in chat.prompt
    assert "RC 权威节点" in chat.prompt
    assert "SUB_ARGUMENT_OF" in chat.prompt
    graph_query.subgraph_for_question.assert_called_once()


@pytest.mark.asyncio
async def test_qa_stream_falls_back_to_graph_query_when_rc_subgraph_missing(
    store_with_graph: GraphStore,
) -> None:
    """V1 / legacy path: empty RC subgraph triggers GraphQuery fallback."""
    rc = RetrievalContext(scale=QuestionScale.DETAIL)

    graph_query = MagicMock()
    graph_query.subgraph_for_question.return_value = {
        "nodes": [{"id": "n1", "label": "核心论点", "type": "Thesis"}],
        "edges": [],
    }

    llm, chat = _capturing_llm("回答[CITE:n1]。")
    engine = _GraphQaEngine(store=store_with_graph, llm=llm, query=graph_query)

    events = [
        evt
        async for evt in engine.stream(
            "hss-001",
            "这篇论文的核心论点是什么？",
            retrieval_context=rc,
        )
    ]

    assert not any(evt.event == "error" for evt in events)
    assert "[n1]" in chat.prompt
    graph_query.subgraph_for_question.assert_called_once()
