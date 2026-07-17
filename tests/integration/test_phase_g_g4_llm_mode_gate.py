# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""G.4 integration gate: LLM_MODE=mock pipeline uses real AgentService without live LLM calls."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from backend.config import get_settings
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

_LIVE_LLM_FORBIDDEN = "live LLM must not be called when LLM_MODE=mock"


@pytest.fixture
def mock_mode_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setenv("CLASSIFIER_LLM_ENABLED", "true")
    monkeypatch.setenv("CLASSIFIER_HEURISTIC_FALLBACK", "true")
    monkeypatch.setenv("EXTRACT_LLM_ENABLED", "true")
    monkeypatch.setenv("EXTRACT_HEURISTIC_FALLBACK", "true")
    monkeypatch.setenv("INGEST_HEAD_LLM_ENABLED", "true")
    get_settings.cache_clear()
    reset_llm_client_cache()


@pytest.mark.asyncio
async def test_g4_mock_pipeline_real_agent_never_invokes_classify_or_extract_llm(
    integration_paper: tuple[str, Path],
    mock_mode_env: None,
) -> None:
    _ = mock_mode_env
    paper_id, pdf_path = integration_paper
    real_agent = AgentService()
    classify_llm_guard = AsyncMock(side_effect=AssertionError(_LIVE_LLM_FORBIDDEN))
    extract_llm_guard = AsyncMock(side_effect=AssertionError(_LIVE_LLM_FORBIDDEN))

    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["ingest"].ingest = AsyncMock(
            return_value={
                "paper_id": paper_id,
                "full_text": STEM_SNIPPET,
                "classifier_input": STEM_SNIPPET,
            },
        )
        with (
            patch("backend.graph.nodes.get_agent_service", return_value=real_agent),
            patch("backend.agents.classifier.classify_with_llm", classify_llm_guard),
            patch("backend.agents.extractor.extract_with_llm", extract_llm_guard),
        ):
            final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("failed") is not True
    assert final.get("classify_warnings", []) == []
    assert final.get("extract_warnings", []) == []

    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.READY
    classify_llm_guard.assert_not_awaited()
    extract_llm_guard.assert_not_awaited()
