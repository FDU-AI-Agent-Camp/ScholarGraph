"""Tests for dynamic node masking in edge extraction."""

from __future__ import annotations

import pytest

from backend.agents.extract_edges import _anchor_prompt, _filter_nodes_for_chunk
from backend.schemas.extract_phase import ExtractedNode, ExtractedNodeList
from backend.schemas.paradigm import Paradigm


_COUNTERS: dict[str, int] = {}


def _nodes(count: int, paradigm: Paradigm, type_name: str) -> list[ExtractedNode]:
    _COUNTERS.setdefault(type_name, 0)
    nodes = []
    for _ in range(count):
        idx = _COUNTERS[type_name]
        _COUNTERS[type_name] = idx + 1
        nodes.append(ExtractedNode(id=f"{type_name.lower()}_{idx}", label=f"Node {idx}", type=type_name))
    return nodes


class TestFilterNodesForChunk:
    def test_no_masking_when_below_threshold(self) -> None:
        nodes = ExtractedNodeList(
            paradigm=Paradigm.STEM,
            nodes=_nodes(10, Paradigm.STEM, "ResearchQuestion"),
        )
        filtered = _filter_nodes_for_chunk(nodes, "Results")
        assert len(filtered.nodes) == 10

    def test_stem_results_masks_research_question(self) -> None:
        nodes = ExtractedNodeList(
            paradigm=Paradigm.STEM,
            nodes=[
                *_nodes(80, Paradigm.STEM, "ResearchQuestion"),
                *_nodes(80, Paradigm.STEM, "Method"),
            ],
        )
        filtered = _filter_nodes_for_chunk(nodes, "Results")
        assert len(filtered.nodes) == 80
        assert all(n.type != "ResearchQuestion" for n in filtered.nodes)

    def test_hss_theoretical_framework_masks_object_or_data(self) -> None:
        nodes = ExtractedNodeList(
            paradigm=Paradigm.HSS,
            nodes=[
                *_nodes(80, Paradigm.HSS, "ObjectOrData"),
                *_nodes(80, Paradigm.HSS, "AnalyticalLens"),
            ],
        )
        filtered = _filter_nodes_for_chunk(nodes, "Theoretical Framework")
        assert len(filtered.nodes) == 80
        assert all(n.type != "ObjectOrData" for n in filtered.nodes)

    def test_unknown_chunk_title_returns_all(self) -> None:
        nodes = ExtractedNodeList(
            paradigm=Paradigm.STEM,
            nodes=[
                *_nodes(80, Paradigm.STEM, "ResearchQuestion"),
                *_nodes(80, Paradigm.STEM, "Method"),
            ],
        )
        filtered = _filter_nodes_for_chunk(nodes, "Appendix")
        assert len(filtered.nodes) == 160


class TestAnchorPrompt:
    def test_contains_strict_id_rules(self) -> None:
        prompt = _anchor_prompt('[{"id":"n1"}]')
        assert "全局实体通讯录" in prompt
        assert "必须且只能从上述通讯录中严格复制" in prompt
        assert "绝不允许创造新的 ID" in prompt
