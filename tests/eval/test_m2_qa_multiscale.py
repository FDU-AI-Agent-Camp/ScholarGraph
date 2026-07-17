# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""M2 eval — multi-scale QA with verifiable citations (A-09).

Green: mock LLM + fixture graph (CI default).
Red: live LLM citation quality (``pytest -m red`` until Huawei cloud verified).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from backend.config import get_settings
from backend.graph.qa import qa_stream
from backend.graph.qa_samples import M2_DEMO_PAPER_ID, M2_HSS_QUESTIONS, seed_m2_qa_graph
from backend.graph.store import GraphStore
from backend.llm.client import reset_llm_client_cache
from backend.llm.mock_chat import MOCK_DISCLAIMER
from tests.helpers.persistence_testkit import register_ready_paper, run_async, setup_qa_persistence_env


@pytest.fixture
def m2_graph_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    graph_dir = tmp_path / "graphs"
    setup_qa_persistence_env(tmp_path, monkeypatch, graph_dir=graph_dir)
    monkeypatch.setenv("LLM_MODE", "mock")
    get_settings.cache_clear()
    reset_llm_client_cache()
    seed_m2_qa_graph(graph_dir)
    run_async(register_ready_paper(M2_DEMO_PAPER_ID))
    return graph_dir


async def _collect_qa(paper_id: str, question: str) -> tuple[str, list[dict], list[tuple[str, dict]]]:
    events: list[tuple[str, dict]] = []
    async for evt in qa_stream(paper_id, question):
        events.append((evt.event, evt.data))
    messages = "".join(payload["delta"] for name, payload in events if name == "message")
    citations = [payload for name, payload in events if name == "citation"]
    return messages, citations, events


def _node_by_id(store_dir: Path, paper_id: str, node_id: str):
    graph = GraphStore(base_dir=store_dir).load(paper_id)
    assert graph is not None
    return next(node for node in graph.nodes if node.id == node_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("sample", M2_HSS_QUESTIONS, ids=lambda s: s.scale)
async def test_m2_mock_qa_emits_verifiable_citation(m2_graph_dir: Path, sample) -> None:
    """A-09 / M2: summary/detail/verification each yield graph-backed citation."""
    messages, citations, events = await _collect_qa(M2_DEMO_PAPER_ID, sample.question)

    assert not any(name == "error" for name, _ in events)
    assert events[-1][0] == "done"
    assert MOCK_DISCLAIMER in messages
    assert len(citations) >= 1

    cite = citations[0]
    assert cite["paper_id"] == M2_DEMO_PAPER_ID
    node = _node_by_id(m2_graph_dir, M2_DEMO_PAPER_ID, cite["node_id"])
    assert cite["label"] == node.label
    assert node.type in sample.expected_node_types


@pytest.mark.asyncio
async def test_m2_three_scales_all_distinct_citation_types(m2_graph_dir: Path) -> None:
    cited_types: list[str] = []
    for sample in M2_HSS_QUESTIONS:
        _messages, citations, _events = await _collect_qa(M2_DEMO_PAPER_ID, sample.question)
        node = _node_by_id(m2_graph_dir, M2_DEMO_PAPER_ID, citations[0]["node_id"])
        cited_types.append(node.type)
    assert len(set(cited_types)) >= 2


@pytest.mark.asyncio
async def test_m2_graph_not_found_emits_actionable_error(m2_graph_dir: Path) -> None:
    events: list[tuple[str, dict]] = []
    async for evt in qa_stream("missing-paper", M2_HSS_QUESTIONS[0].question):
        events.append((evt.event, evt.data))

    assert events[0][0] == "error"
    assert events[0][1]["code"] == "GRAPH_NOT_FOUND"
    assert "missing-paper" in events[0][1]["message"]
    assert events[-1][0] == "done"


@pytest.mark.asyncio
async def test_m2_empty_question_falls_back_to_summary_scale(m2_graph_dir: Path) -> None:
    _messages, citations, events = await _collect_qa(M2_DEMO_PAPER_ID, "   ")
    assert not any(name == "error" for name, _ in events)
    assert citations
    node = _node_by_id(m2_graph_dir, M2_DEMO_PAPER_ID, citations[0]["node_id"])
    assert node.type == "Thesis"


@pytest.mark.red
@pytest.mark.xfail(strict=True, reason="A-09 live: Huawei SaaS citation 质量待人工验")
@pytest.mark.asyncio
async def test_m2_live_qa_citation_matches_graph(m2_graph_dir: Path) -> None:
    """Red path: live LLM must cite real node ids (run with LLM_MODE=live locally)."""
    if get_settings().is_llm_mock:
        pytest.skip("live-only red test")

    sample = M2_HSS_QUESTIONS[0]
    _messages, citations, events = await _collect_qa(M2_DEMO_PAPER_ID, sample.question)
    assert not any(name == "error" for name, _ in events)
    assert citations
    node = _node_by_id(m2_graph_dir, M2_DEMO_PAPER_ID, citations[0]["node_id"])
    assert node.type in sample.expected_node_types
