"""F.3 integration: STEM extract produces verification-chain structure."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE
from backend.agents.extractor import extract
from backend.config import get_settings
from backend.llm.client import reset_llm_client_cache
from backend.schemas.paradigm import Paradigm

from tests.helpers.f33_stem_graphs import assert_f33_stem_core_structure, assert_stem_schema_whitelist

pytestmark = pytest.mark.integration

STEM_SAMPLE = (
    "Title: GNN Benchmark\n"
    "We study the node classification task. Our method uses a graph neural network. "
    "Experiments on Cora dataset with accuracy metric and GCN baseline. "
    "Results outperform prior work on the benchmark."
)


@pytest.fixture
def live_extract_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("EXTRACT_LLM_ENABLED", "true")
    monkeypatch.setenv("EXTRACT_HEURISTIC_FALLBACK", "true")
    get_settings.cache_clear()
    reset_llm_client_cache()


@pytest.mark.asyncio
async def test_f33_stem_extract_fallback_graph_matches_verification_chain(live_extract_env: None) -> None:
    _ = live_extract_env

    with patch(
        "backend.agents.extractor.extract_with_llm",
        new=AsyncMock(side_effect=RuntimeError("llm unavailable")),
    ):
        result = await extract(STEM_SAMPLE, Paradigm.STEM, paper_id="f33-int-stem-fallback")

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings
    assert_stem_schema_whitelist(result.graph)
    assert_f33_stem_core_structure(result.graph)
    node_types = {node.type for node in result.graph.nodes}
    for hss_only in ("Thesis", "AnalyticalLens", "IntellectualContext", "ObjectOrData"):
        assert hss_only not in node_types
