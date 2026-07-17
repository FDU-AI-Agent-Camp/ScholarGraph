# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""B7 shadow diff — V1 GraphQuery path vs V2 RetrievalContext path (M2 pure graph)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from difflib import unified_diff
from pathlib import Path

import pytest
from backend.config import get_settings
from backend.graph.qa import qa_stream
from backend.graph.qa_v2 import subgraph_sections_shadow_fingerprint
from backend.graph.store import GraphStore
from backend.llm.client import reset_llm_client_cache
from backend.rag.hybrid_retriever import HybridRetriever
from backend.rag.models import QuestionScale, RetrievalContext

from tests.graph.test_qa import _FakeChunk
from tests.helpers.persistence_testkit import register_ready_paper, run_async, setup_qa_persistence_env


class _CapturingFakeChat:
    def __init__(self) -> None:
        self.prompt = ""

    async def astream(self, prompt: str) -> AsyncIterator[_FakeChunk]:
        self.prompt = prompt
        yield _FakeChunk("影子对比[CITE:n1]。")


def _capturing_llm() -> tuple[object, _CapturingFakeChat]:
    chat = _CapturingFakeChat()
    client = type("ShadowCapturingLlmClient", (), {})()
    client.chat = chat
    return client, chat


async def _capture_prompt(
    paper_id: str,
    question: str,
    *,
    retrieval_context: RetrievalContext | None,
) -> str:
    llm, chat = _capturing_llm()
    async for _evt in qa_stream(
        paper_id,
        question,
        retrieval_context=retrieval_context,
        llm=llm,
    ):
        pass
    return chat.prompt


def _shadow_diff_lines(left: str, right: str) -> list[str]:
    return list(
        unified_diff(
            left.splitlines(keepends=True),
            right.splitlines(keepends=True),
            fromfile="v1",
            tofile="v2",
        )
    )


@pytest.fixture
def shadow_graph_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> GraphStore:
    from tests.rag.test_context_source_unification import _seed_graph_store

    graph_dir = tmp_path / "graphs"
    setup_qa_persistence_env(tmp_path, monkeypatch, graph_dir=graph_dir)
    monkeypatch.setenv("LLM_MODE", "mock")
    get_settings.cache_clear()
    reset_llm_client_cache()

    store = _seed_graph_store(graph_dir)
    run_async(register_ready_paper("hss-001"))
    return store


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question",
    [
        "分论点如何支撑核心论点？",
        "这篇论文的核心论点是什么？",
        "历史制度主义如何审视核心论点？",
    ],
)
async def test_v1_v2_shadow_subgraph_fingerprint_diff_is_zero(
    shadow_graph_env: GraphStore,
    question: str,
) -> None:
    """M2 pure graph: V1 live GraphQuery vs V2 RC SSOT must match after normalization."""
    graph = shadow_graph_env.load("hss-001")
    assert graph is not None

    retriever = HybridRetriever(vector_store=None)
    rc = await retriever.retrieve(
        "hss-001",
        question,
        graph,
        scale=QuestionScale.SUMMARY,
    )
    assert rc.nodes, "V2 path must carry graph subgraph in RC"

    v1_prompt = await _capture_prompt("hss-001", question, retrieval_context=None)
    v2_prompt = await _capture_prompt("hss-001", question, retrieval_context=rc)

    v1_fp = subgraph_sections_shadow_fingerprint(v1_prompt)
    v2_fp = subgraph_sections_shadow_fingerprint(v2_prompt)

    assert v1_fp == v2_fp, (
        f"Shadow diff must be zero for {question!r}\n"
        f"nodes diff:\n{''.join(_shadow_diff_lines(v1_fp[0], v2_fp[0]))}\n"
        f"edges diff:\n{''.join(_shadow_diff_lines(v1_fp[1], v2_fp[1]))}"
    )


@pytest.mark.asyncio
async def test_v1_v2_shadow_diff_survives_shuffled_rc_subgraph_order(
    shadow_graph_env: GraphStore,
) -> None:
    """Normalization must tolerate RC list order permutations (set-like retrieval)."""
    question = "分论点如何支撑核心论点？"
    graph = shadow_graph_env.load("hss-001")
    assert graph is not None

    retriever = HybridRetriever(vector_store=None)
    rc = await retriever.retrieve("hss-001", question, graph, scale=QuestionScale.SUMMARY)

    shuffled = rc.model_copy(
        update={
            "nodes": list(reversed(rc.nodes)),
            "edges": list(reversed(rc.edges)),
        },
    )

    v1_prompt = await _capture_prompt("hss-001", question, retrieval_context=None)
    v2_prompt = await _capture_prompt("hss-001", question, retrieval_context=shuffled)

    assert subgraph_sections_shadow_fingerprint(v1_prompt) == subgraph_sections_shadow_fingerprint(v2_prompt)


@pytest.mark.asyncio
async def test_v1_v2_shadow_diff_with_fixture_graph_hss(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shadow parity on the richer OpenAPI ``graph-hss.json`` fixture."""
    import json

    from backend.schemas.graph import UnifiedPaperGraph

    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_dir))
    monkeypatch.setenv("LLM_MODE", "mock")
    get_settings.cache_clear()
    reset_llm_client_cache()

    fixture_path = Path(__file__).resolve().parents[2] / "docs" / "api" / "fixtures" / "graph-hss.json"
    graph_payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    graph = UnifiedPaperGraph.model_validate(graph_payload["data"])
    graph = graph.model_copy(update={"paper_id": "hss-001"})

    store = GraphStore(base_dir=graph_dir)
    store.save(graph)

    question = "分论点如何支撑核心论点？"
    retriever = HybridRetriever(vector_store=None)
    rc = await retriever.retrieve("hss-001", question, graph, scale=QuestionScale.SUMMARY)

    v1_prompt = await _capture_prompt("hss-001", question, retrieval_context=None)
    v2_prompt = await _capture_prompt("hss-001", question, retrieval_context=rc)

    assert subgraph_sections_shadow_fingerprint(v1_prompt) == subgraph_sections_shadow_fingerprint(v2_prompt)
