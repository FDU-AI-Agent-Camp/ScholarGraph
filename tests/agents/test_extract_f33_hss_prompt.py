# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Phase F.3 unit tests: HSS prompt definitions, heuristic shape, LLM prompt wiring."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from backend.agents.extract_heuristic import build_hss_graph
from backend.agents.extract_llm import load_extract_prompt
from backend.config import get_settings
from backend.llm.client import reset_llm_client_cache
from backend.schemas import NodeType
from backend.schemas.paradigm import Paradigm
from tests.helpers.f33_hss_graphs import (
    F33_FORBIDDEN_STEM_NODE_TYPES,
    F33_HSS_CORE_EDGE_TYPES,
    assert_f33_core_structure,
    assert_hss_excludes_stem_only_node_types,
    assert_hss_schema_whitelist,
    minimal_f33_hss_graph,
)

F33_HSS_NODE_TYPES = (
    "Thesis",
    "SubArgument",
    "AnalyticalLens",
    "ObjectOrData",
    "IntellectualContext",
    "Claim",
    "Evidence",
)

F33_HSS_EDGE_TYPES = (
    "SUB_ARGUMENT_OF",
    "CHALLENGES",
    "EXAMINES_THROUGH",
    "LENS_OF",
    "INFORMS",
    "SUPPORTS",
)


def test_f33_hss_prompt_lists_all_node_types() -> None:
    prompt = load_extract_prompt(Paradigm.HSS)
    for node_type in F33_HSS_NODE_TYPES:
        assert node_type in prompt, f"missing HSS node type {node_type}"


def test_f33_hss_prompt_lists_core_edge_types() -> None:
    prompt = load_extract_prompt(Paradigm.HSS)
    for edge_type in F33_HSS_EDGE_TYPES:
        assert edge_type in prompt, f"missing HSS edge type {edge_type}"


def test_f33_hss_prompt_documents_edge_semantics_in_chinese() -> None:
    prompt = load_extract_prompt(Paradigm.HSS)
    for phrase in ("分论点支撑核心论点", "本文论点挑战既有解释", "以某理论审视对象/材料"):
        assert phrase in prompt, f"missing HSS edge semantics: {phrase}"


def test_f33_hss_prompt_specifies_node_counts() -> None:
    prompt = load_extract_prompt(Paradigm.HSS)
    assert "Exactly 1" in prompt or "exactly 1" in prompt.lower()
    assert "3–5" in prompt or "3-5" in prompt
    assert "0–2" in prompt or "0-2" in prompt


def test_f33_hss_prompt_forbids_stem_node_types() -> None:
    prompt = load_extract_prompt(Paradigm.HSS)
    assert "Forbidden node types" in prompt or "Do not use" in prompt
    for forbidden in F33_FORBIDDEN_STEM_NODE_TYPES:
        assert forbidden in prompt, f"prompt must forbid STEM-only type {forbidden}"


def test_f33_hss_prompt_explicitly_lists_metric_baseline_dataset_as_forbidden() -> None:
    prompt = load_extract_prompt(Paradigm.HSS)
    forbidden_section = prompt.split("Forbidden node types", 1)[-1]
    for stem_type in ("Metric", "Baseline", "Dataset"):
        assert stem_type in forbidden_section


def test_f33_hss_prompt_documents_argumentation_tree() -> None:
    prompt = load_extract_prompt(Paradigm.HSS)
    assert "argumentation tree" in prompt.lower() or "论证树" in prompt


def test_f33_hss_prompt_documents_secondary_edges() -> None:
    prompt = load_extract_prompt(Paradigm.HSS)
    for edge_type in ("CONTEXTUALIZES", "RELATES_TO", "REF"):
        assert edge_type in prompt


def test_f33_minimal_fixture_graph_passes_f33_structure() -> None:
    graph = minimal_f33_hss_graph()
    assert_hss_schema_whitelist(graph)
    assert_f33_core_structure(graph, min_sub_arguments=3)
    edge_types = {edge.type for edge in graph.edges}
    assert {"SUB_ARGUMENT_OF", "EXAMINES_THROUGH", "CHALLENGES", "LENS_OF"} <= edge_types
    assert edge_types <= F33_HSS_CORE_EDGE_TYPES | {"CONTEXTUALIZES", "RELATES_TO", "REF"}


def test_f33_build_hss_heuristic_matches_core_f33_shape() -> None:
    graph = build_hss_graph(
        "标题：测试\n本文认为核心论点成立。首先，分论点一。其次，分论点二。再次，分论点三。\n"
        "既有研究忽略了地方制度。历史制度主义视角下分析通商口岸档案。",
        "测试",
    )
    assert_hss_schema_whitelist(graph)
    assert_hss_excludes_stem_only_node_types(graph)
    assert_f33_core_structure(graph, min_sub_arguments=2)
    node_types = {node.type for node in graph.nodes}
    assert NodeType.INTELLECTUAL_CONTEXT in node_types
    assert any(edge.type == "CHALLENGES" for edge in graph.edges)
    assert any(edge.type == "EXAMINES_THROUGH" for edge in graph.edges)
    assert sum(1 for node in graph.nodes if node.type == NodeType.THESIS) == 1


@pytest.mark.asyncio
async def test_f33_extract_with_llm_system_prompt_includes_f33_definitions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    get_settings.cache_clear()
    reset_llm_client_cache()

    captured: dict[str, str] = {}

    async def _capture_invoke(_client, *, system_prompt, user_content, use_fallback_model):
        captured["system_prompt"] = system_prompt
        return minimal_f33_hss_graph(paper_id="p")

    with patch("backend.agents.extract_llm._invoke_structured", side_effect=_capture_invoke):
        from backend.agents.extract_llm import extract_with_llm

        await extract_with_llm("body", Paradigm.HSS, paper_id="f33-prompt-wire")

    prompt = captured["system_prompt"]
    assert "F.3 Operational node definitions" in prompt
    assert "SUB_ARGUMENT_OF" in prompt
    assert "Exactly 1" in prompt or "exactly 1" in prompt.lower()

    get_settings.cache_clear()
    reset_llm_client_cache()
