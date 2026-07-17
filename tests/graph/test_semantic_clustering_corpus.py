# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Regression tests using real corpus extraction outputs.

These tests load the ExtractedGraph fixtures produced by
``scripts/validate_semantic_clustering_corpus.py`` and check that the
post-refactor ``_node_text()`` and clustering logic do not reintroduce the
over/under-merging patterns described in ``progress-v2.md``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from backend.graph.semantic_clustering import _node_text
from backend.schemas.extract_phase import ExtractedGraph

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "data" / "benchmark_reports" / "semantic_clustering_validation"


@pytest.fixture
def hss_001_graph() -> ExtractedGraph:
    path = FIXTURE_DIR / "hss-001.extracted.json"
    if not path.exists():
        pytest.skip(f"Missing corpus fixture: {path}; run scripts/validate_semantic_clustering_corpus.py")
    return ExtractedGraph.model_validate_json(path.read_text(encoding="utf-8"))


@pytest.fixture
def hss_003_graph() -> ExtractedGraph:
    path = FIXTURE_DIR / "hss-003.extracted.json"
    if not path.exists():
        pytest.skip(f"Missing corpus fixture: {path}; run scripts/validate_semantic_clustering_corpus.py")
    return ExtractedGraph.model_validate_json(path.read_text(encoding="utf-8"))


class TestNodeTextUsesCleanStructuredTemplate:
    """Verify that _node_text no longer leaks raw source_span into embeddings."""

    def test_hss_001_node_text_excludes_source_span(self, hss_001_graph: ExtractedGraph) -> None:
        for node in hss_001_graph.nodes:
            text = _node_text(node)
            assert "补充说明" not in text
            assert "source_span" not in text
            if node.source_span:
                assert node.source_span[:30] not in text
            assert text.startswith(f"类型: {node.type}")
            assert "细分类别:" in text
            assert "核心概念:" in text

    def test_hss_003_node_text_excludes_source_span(self, hss_003_graph: ExtractedGraph) -> None:
        for node in hss_003_graph.nodes:
            text = _node_text(node)
            assert "补充说明" not in text
            if node.source_span:
                assert node.source_span[:30] not in text
            assert text.startswith(f"类型: {node.type}")


class TestTypeFirewallHoldsOnCorpusFixtures:
    """Cross-type merges are only allowed for the whitelisted child->parent rules."""

    @pytest.mark.parametrize(
        ("fixture_name",),
        [
            ("hss_001_graph",),
            ("hss_003_graph",),
        ],
    )
    def test_semantic_aliases_respect_type_firewall(
        self,
        request: pytest.FixtureRequest,
        fixture_name: str,
    ) -> None:
        graph: ExtractedGraph = request.getfixturevalue(fixture_name)
        allowed_cross_type = {
            ("SubArgument", "Claim"),
            ("Dataset", "Method"),
            ("Metric", "Method"),
            ("Baseline", "Method"),
            ("ResearchQuestion", "Thesis"),
        }
        for node in graph.nodes:
            aliases = node.data.get("semantic_aliases", [])
            for alias in aliases:
                alias_type = alias.get("type")
                if alias_type == node.type:
                    continue
                assert (alias_type, node.type) in allowed_cross_type, (
                    f"Forbidden cross-type merge: {alias_type} -> {node.type} "
                    f"(root={node.label!r}, alias={alias.get('label')!r})"
                )


@pytest.mark.red
class TestReportArtifactsExist:
    """Ensure the validation script produced the expected outputs."""

    def test_extracted_fixtures_and_report_exist(self) -> None:
        assert (FIXTURE_DIR / "hss-001.extracted.json").exists()
        assert (FIXTURE_DIR / "hss-003.extracted.json").exists()
        report_path = FIXTURE_DIR / "report.md"
        assert report_path.exists()
        content = report_path.read_text(encoding="utf-8")
        assert "hss-001" in content
        assert "hss-003" in content
        assert "Potential over-merging" in content
        assert "Potential under-merging" in content
