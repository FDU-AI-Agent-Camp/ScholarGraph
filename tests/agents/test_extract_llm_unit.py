"""Unit tests: extract_llm helpers and structured invoke."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from backend.agents.extract_llm import (
    _validate_llm_graph,
    build_user_payload,
    extract_with_llm,
    load_extract_prompt,
    truncate_full_text,
)
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm


def test_truncate_full_text_no_truncation_when_under_limit() -> None:
    text, truncated = truncate_full_text("short", max_chars=100)
    assert text == "short"
    assert truncated is False


def test_truncate_full_text_zero_limit_keeps_full_text() -> None:
    text, truncated = truncate_full_text("abcdef", max_chars=0)
    assert text == "abcdef"
    assert truncated is False


def test_load_extract_prompt_reads_hss_and_stem_files() -> None:
    hss = load_extract_prompt(Paradigm.HSS)
    stem = load_extract_prompt(Paradigm.STEM)
    assert "Thesis" in hss
    assert "Method" in stem or "ResearchQuestion" in stem


def test_build_user_payload_omits_document_head_when_empty() -> None:
    payload = json.loads(
        build_user_payload(
            full_text="body",
            paradigm=Paradigm.HSS,
            paper_id="p1",
            title="T",
            head_context="   ",
            max_chars=100,
        ),
    )
    assert "document_head" not in payload


def test_build_user_payload_marks_truncated_flag() -> None:
    payload = json.loads(
        build_user_payload(
            full_text="x" * 50,
            paradigm=Paradigm.STEM,
            paper_id="p1",
            title="T",
            head_context=None,
            max_chars=10,
        ),
    )
    assert payload["truncated"] is True
    assert len(payload["full_text"]) == 10
    assert payload["paradigm"] == "STEM"


def test_validate_llm_graph_rejects_empty_nodes() -> None:
    graph = UnifiedPaperGraph(paper_id="p", paradigm=Paradigm.HSS, nodes=[], edges=[])
    with pytest.raises(ValueError, match="no nodes"):
        _validate_llm_graph(graph, expected_paradigm=Paradigm.HSS)


def test_validate_llm_graph_rejects_empty_edges() -> None:
    graph = UnifiedPaperGraph(
        paper_id="p",
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="t", type="Thesis")],
        edges=[],
    )
    with pytest.raises(ValueError, match="no edges"):
        _validate_llm_graph(graph, expected_paradigm=Paradigm.HSS)


def test_validate_llm_graph_rejects_paradigm_mismatch() -> None:
    graph = UnifiedPaperGraph(
        paper_id="p",
        paradigm=Paradigm.STEM,
        nodes=[GraphNode(id="n1", label="m", type="Method")],
        edges=[GraphEdge(id="e1", source="n1", target="n1", label="RELATES_TO", type="RELATES_TO")],
    )
    with pytest.raises(ValueError, match="paradigm"):
        _validate_llm_graph(graph, expected_paradigm=Paradigm.HSS)


@pytest.mark.asyncio
async def test_extract_with_llm_retries_fallback_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    from backend.config import get_settings
    from backend.llm.client import LlmClient, reset_llm_client_cache

    get_settings.cache_clear()
    reset_llm_client_cache()

    valid_graph = UnifiedPaperGraph(
        paper_id="p1",
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="论点", type="Thesis")],
        edges=[GraphEdge(id="e1", source="n1", target="n1", label="REF", type="REF")],
    )

    primary_runnable = MagicMock()
    primary_runnable.ainvoke = AsyncMock(side_effect=RuntimeError("primary failed"))
    fallback_runnable = MagicMock()
    fallback_runnable.ainvoke = AsyncMock(return_value=valid_graph)

    primary_chat = MagicMock()
    primary_chat.with_structured_output.return_value = primary_runnable
    fallback_chat = MagicMock()
    fallback_chat.with_structured_output.return_value = fallback_runnable

    client = LlmClient()
    client._chat = primary_chat
    client._fallback_chat = fallback_chat

    graph = await extract_with_llm(
        "标题：测试\n本文认为……",
        Paradigm.HSS,
        paper_id="p1",
        llm_client=client,
    )

    assert graph.paper_id == "p1"
    assert graph.nodes[0].type == "Thesis"
    primary_runnable.ainvoke.assert_awaited_once()
    fallback_runnable.ainvoke.assert_awaited_once()

    get_settings.cache_clear()
    reset_llm_client_cache()
