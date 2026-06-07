"""F.3 integration: STEM extract produces verification-chain structure."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE
from backend.agents.extractor import extract
from backend.config import get_settings
from backend.graph.store import GraphStore
from backend.graph.workflow import run_paper_pipeline
from backend.llm.client import reset_llm_client_cache
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.agent_service import AgentService
from backend.services.paper_service import get_paper_service

from tests.conftest import mock_pipeline_node_services
from tests.helpers.f33_stem_graphs import (
    assert_f33_stem_core_structure,
    assert_stem_excludes_hss_only_node_types,
    assert_stem_schema_whitelist,
)

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
    assert_stem_excludes_hss_only_node_types(result.graph)
    assert_f33_stem_core_structure(result.graph)


@pytest.mark.asyncio
async def test_f33_stem_pipeline_stores_graph_without_hss_only_types(
    integration_paper: tuple[str, Path],
    live_extract_env: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = live_extract_env
    paper_id, pdf_path = integration_paper
    monkeypatch.setenv("GRAPH_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()

    agent = AgentService()
    agent.classify_paradigm = AsyncMock(  # type: ignore[method-assign]
        return_value=ParadigmClassification(paradigm=Paradigm.STEM, confidence=0.9, reason="mock"),
    )

    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["ingest"].ingest = AsyncMock(
            return_value={
                "paper_id": paper_id,
                "full_text": STEM_SAMPLE,
                "classifier_input": "snippet",
            },
        )
        with (
            patch("backend.graph.nodes.get_agent_service", return_value=agent),
            patch(
                "backend.agents.extractor.extract_with_llm",
                new=AsyncMock(side_effect=RuntimeError("structured output failed")),
            ),
        ):
            final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("failed") is not True
    assert EXTRACT_HEURISTIC_FALLBACK_CODE in final.get("extract_warnings", [])

    stored = GraphStore(base_dir=tmp_path).load(paper_id)
    assert stored is not None
    assert stored.paradigm == Paradigm.STEM
    assert_stem_schema_whitelist(stored)
    assert_stem_excludes_hss_only_node_types(stored)
    assert_f33_stem_core_structure(stored)

    status = await get_paper_service().get_status(paper_id)
    assert status.extract_warnings == [EXTRACT_HEURISTIC_FALLBACK_CODE]

    get_settings.cache_clear()
