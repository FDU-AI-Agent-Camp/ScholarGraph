"""G.0 product decision integration: classify fallback must not fail pipeline."""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from backend.agents.classifier_constants import CLASSIFIER_HEURISTIC_FALLBACK_CODE
from backend.config import get_settings
from backend.graph import nodes
from backend.graph.workflow import run_paper_pipeline
from backend.llm.client import reset_llm_client_cache
from backend.schemas.paper import PaperStatus
from backend.services.agent_service import AgentService
from backend.services.paper_service import get_paper_service

from tests.conftest import mock_pipeline_node_services

pytestmark = pytest.mark.integration

STEM_SNIPPET = (
    "Title: Agent framework benchmark. We evaluate the model on datasets with accuracy, "
    "F1 metrics, baselines, and ablation experiments."
)


@pytest.fixture
def live_classify_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("CLASSIFIER_LLM_ENABLED", "true")
    monkeypatch.setenv("CLASSIFIER_HEURISTIC_FALLBACK", "true")
    get_settings.cache_clear()
    reset_llm_client_cache()


def test_g0_integration_classify_node_only_reads_classifier_input_from_state() -> None:
    """G.0: classify 节点不改动 classifier_input 拼装。"""
    source = inspect.getsource(nodes.classify_node)
    assert 'state["classifier_input"]' in source
    assert "merge_with_rules" not in source


@pytest.mark.asyncio
async def test_g0_integration_llm_failure_fallback_pipeline_reaches_ready(
    integration_paper: tuple[str, Path],
    live_classify_env: None,
) -> None:
    """G.0: LLM 失败 → heuristic fallback → 流水线不 failed。"""
    _ = live_classify_env
    paper_id, pdf_path = integration_paper
    agent = AgentService()

    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["ingest"].ingest = AsyncMock(
            return_value={
                "paper_id": paper_id,
                "full_text": STEM_SNIPPET,
                "classifier_input": STEM_SNIPPET,
            },
        )
        with (
            patch("backend.graph.nodes.get_agent_service", return_value=agent),
            patch(
                "backend.agents.classifier.classify_with_llm",
                new=AsyncMock(side_effect=RuntimeError("structured output failed")),
            ),
        ):
            final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("failed") is not True
    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.READY
    assert status.classify_warnings == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]
