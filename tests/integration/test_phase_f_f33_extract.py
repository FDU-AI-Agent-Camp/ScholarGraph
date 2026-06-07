"""F.3 integration: HSS extract produces F.3 argumentation-tree structure."""

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
from tests.helpers.f33_hss_graphs import (
    assert_f33_core_structure,
    assert_hss_excludes_stem_only_node_types,
    assert_hss_schema_whitelist,
)

pytestmark = pytest.mark.integration

HSS_SAMPLE = (
    "标题：近代口岸制度研究\n"
    "本文认为通商口岸体现制度路径依赖。\n"
    "首先，口岸开放重塑了地方治理结构。\n"
    "其次，贸易规则形成了路径锁定。\n"
    "再次，档案材料揭示了制度延续性。\n"
    "既有研究忽略了制度变迁中的地方能动性。\n"
    "本文以历史制度主义审视晚清通商口岸档案。"
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
async def test_f33_hss_extract_fallback_graph_matches_core_structure(live_extract_env: None) -> None:
    _ = live_extract_env

    with patch(
        "backend.agents.extractor.extract_with_llm",
        new=AsyncMock(side_effect=RuntimeError("llm unavailable")),
    ):
        result = await extract(HSS_SAMPLE, Paradigm.HSS, paper_id="f33-int-fallback")

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings
    assert_hss_schema_whitelist(result.graph)
    assert_hss_excludes_stem_only_node_types(result.graph)
    assert_f33_core_structure(result.graph, min_sub_arguments=2)
    assert any(edge.type == "CHALLENGES" for edge in result.graph.edges)
    assert any(edge.type == "EXAMINES_THROUGH" for edge in result.graph.edges)


@pytest.mark.asyncio
async def test_f33_pipeline_stores_hss_graph_with_f33_node_types(
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
        return_value=ParadigmClassification(paradigm=Paradigm.HSS, confidence=0.9, reason="mock"),
    )

    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["ingest"].ingest = AsyncMock(
            return_value={
                "paper_id": paper_id,
                "full_text": HSS_SAMPLE,
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
    assert stored.paradigm == Paradigm.HSS
    assert_hss_schema_whitelist(stored)
    assert_hss_excludes_stem_only_node_types(stored)
    assert_f33_core_structure(stored, min_sub_arguments=2)

    status = await get_paper_service().get_status(paper_id)
    assert status.extract_warnings == [EXTRACT_HEURISTIC_FALLBACK_CODE]

    get_settings.cache_clear()
