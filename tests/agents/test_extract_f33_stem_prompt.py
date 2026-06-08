"""Phase F.3 unit tests: STEM prompt definitions, heuristic shape, LLM prompt wiring."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from backend.agents.extract_heuristic import build_stem_graph
from backend.agents.extract_llm import load_extract_prompt
from backend.config import get_settings
from backend.llm.client import reset_llm_client_cache
from backend.schemas import NodeType
from backend.schemas.paradigm import Paradigm
from tests.helpers.f33_stem_graphs import (
    F33_FORBIDDEN_HSS_NODE_TYPES,
    F33_STEM_CORE_EDGE_TYPES,
    assert_f33_stem_core_structure,
    assert_stem_excludes_hss_only_node_types,
    assert_stem_schema_whitelist,
    minimal_f33_stem_graph,
)

F33_STEM_NODE_TYPES = (
    "ResearchQuestion",
    "Method",
    "Dataset",
    "Metric",
    "Baseline",
    "Experiment",
    "Claim",
    "Evidence",
    "Finding",
)


def test_f33_stem_prompt_lists_all_node_types() -> None:
    prompt = load_extract_prompt(Paradigm.STEM)
    for node_type in F33_STEM_NODE_TYPES:
        assert node_type in prompt, f"missing STEM node type {node_type}"


def test_f33_stem_prompt_lists_core_edge_types() -> None:
    prompt = load_extract_prompt(Paradigm.STEM)
    for edge_type in F33_STEM_CORE_EDGE_TYPES:
        assert edge_type in prompt, f"missing STEM edge type {edge_type}"


def test_f33_stem_prompt_documents_edge_semantics_in_chinese() -> None:
    prompt = load_extract_prompt(Paradigm.STEM)
    for phrase in ("方法针对问题", "方法在某数据上评测", "声称由某指标度量", "声称与基线对比", "实验支撑声称"):
        assert phrase in prompt, f"missing STEM edge semantics: {phrase}"


def test_f33_stem_prompt_documents_node_definitions_in_chinese() -> None:
    prompt = load_extract_prompt(Paradigm.STEM)
    for phrase in ("研究问题 / 任务定义", "方法、模型、系统", "性能声称（优于 SOTA 等）", "实验结果、表格结论"):
        assert phrase in prompt, f"missing STEM node definition: {phrase}"


def test_f33_stem_prompt_specifies_node_counts() -> None:
    prompt = load_extract_prompt(Paradigm.STEM)
    assert "Exactly 1" in prompt or "exactly 1" in prompt.lower()
    assert "0–2" in prompt or "0-2" in prompt


def test_f33_stem_prompt_forbids_hss_node_types() -> None:
    prompt = load_extract_prompt(Paradigm.STEM)
    assert "Forbidden node types" in prompt or "Do not use" in prompt
    for forbidden in F33_FORBIDDEN_HSS_NODE_TYPES:
        assert forbidden in prompt, f"prompt must forbid HSS-only type {forbidden}"


def test_f33_stem_prompt_explicitly_lists_analytical_lens_intellectual_context_object_or_data() -> None:
    prompt = load_extract_prompt(Paradigm.STEM)
    forbidden_section = prompt.split("Forbidden node types", 1)[-1]
    for hss_type in ("AnalyticalLens", "IntellectualContext", "ObjectOrData"):
        assert hss_type in forbidden_section


def test_f33_stem_prompt_lists_core_verification_edges_with_direction() -> None:
    prompt = load_extract_prompt(Paradigm.STEM)
    assert "Method` → `ResearchQuestion" in prompt or "Method → ResearchQuestion" in prompt
    assert "Evidence` → `Claim" in prompt or "Evidence → Claim" in prompt


def test_f33_stem_prompt_documents_verification_chain() -> None:
    prompt = load_extract_prompt(Paradigm.STEM)
    assert "verification chain" in prompt.lower() or "验证链" in prompt


def test_f33_minimal_stem_fixture_passes_f33_structure() -> None:
    graph = minimal_f33_stem_graph()
    assert_stem_schema_whitelist(graph)
    assert_f33_stem_core_structure(graph)
    edge_types = {edge.type for edge in graph.edges}
    assert F33_STEM_CORE_EDGE_TYPES <= edge_types


def test_f33_build_stem_heuristic_matches_core_f33_shape() -> None:
    graph = build_stem_graph(
        "Title: ML\nWe study the classification task. Our method uses a Transformer model. "
        "Experiments on GLUE benchmark with F1 metric and BERT baseline comparison. "
        "Results outperform prior work.",
        "ML",
    )
    assert_stem_schema_whitelist(graph)
    assert_stem_excludes_hss_only_node_types(graph)
    assert_f33_stem_core_structure(graph)
    node_types = {node.type for node in graph.nodes}
    assert NodeType.RESEARCH_QUESTION in node_types
    assert any(edge.type == "ADDRESSES" for edge in graph.edges)
    assert any(edge.type == "MEASURED_BY" for edge in graph.edges)
    assert any(edge.type == "COMPARES_TO" for edge in graph.edges)


@pytest.mark.asyncio
async def test_f33_extract_with_llm_system_prompt_includes_stem_f33_definitions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    get_settings.cache_clear()
    reset_llm_client_cache()

    captured: dict[str, str] = {}

    async def _capture_invoke(_client, *, system_prompt, user_content, use_fallback_model):
        captured["system_prompt"] = system_prompt
        return minimal_f33_stem_graph(paper_id="p")

    with patch("backend.agents.extract_llm._invoke_structured", side_effect=_capture_invoke):
        from backend.agents.extract_llm import extract_with_llm

        await extract_with_llm("body", Paradigm.STEM, paper_id="f33-stem-prompt-wire")

    prompt = captured["system_prompt"]
    assert "F.3 Operational node definitions" in prompt
    assert "ADDRESSES" in prompt
    assert "EVALUATED_ON" in prompt

    get_settings.cache_clear()
    reset_llm_client_cache()
