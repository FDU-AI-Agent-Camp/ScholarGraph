# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Integration: classify fallback machine code on status/detail after pipeline (FE polling contract)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from backend.agents.classifier_constants import CLASSIFIER_HEURISTIC_FALLBACK_CODE
from backend.config import get_settings
from backend.graph.workflow import run_paper_pipeline
from backend.llm.client import reset_llm_client_cache
from backend.main import app
from backend.services.agent_service import AgentService
from httpx import ASGITransport, AsyncClient

from tests.conftest import mock_pipeline_node_services

pytestmark = pytest.mark.integration

FROZEN_CODE = "classifier_heuristic_fallback"
FROZEN_MESSAGE = "触发分类启发式Fallback!"
FIXTURES_DIR = Path(__file__).resolve().parents[2] / "docs" / "api" / "fixtures"
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
    monkeypatch.setenv("EXTRACT_LLM_ENABLED", "false")
    get_settings.cache_clear()
    reset_llm_client_cache()


@pytest.fixture
async def api_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_integration_pipeline_fallback_api_exposes_frozen_machine_code_only(
    integration_paper: tuple[str, Path],
    live_classify_env: None,
    api_client: AsyncClient,
) -> None:
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
            await run_paper_pipeline(paper_id, pdf_path)

    status_resp = await api_client.get(f"/api/v1/papers/{paper_id}/status")
    detail_resp = await api_client.get(f"/api/v1/papers/{paper_id}")

    status_data = status_resp.json()["data"]
    detail_data = detail_resp.json()["data"]

    assert status_data["classify_warnings"] == [FROZEN_CODE]
    assert detail_data["classify_warnings"] == [FROZEN_CODE]
    assert FROZEN_MESSAGE not in status_data["classify_warnings"]
    assert FROZEN_MESSAGE not in detail_data["classify_warnings"]
    assert detail_data["classification"]["reason"] != FROZEN_MESSAGE
    assert "classify_warnings" not in detail_data["classification"]


def test_integration_classify_fallback_fixtures_align_with_frozen_code() -> None:
    status_payload = json.loads((FIXTURES_DIR / "paper-status-classify-fallback.json").read_text(encoding="utf-8"))
    detail_payload = json.loads((FIXTURES_DIR / "paper-detail-classify-fallback.json").read_text(encoding="utf-8"))

    assert status_payload["data"]["classify_warnings"] == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]
    assert detail_payload["data"]["classify_warnings"] == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]
    assert FROZEN_MESSAGE not in json.dumps(status_payload, ensure_ascii=False)
    assert FROZEN_MESSAGE not in json.dumps(detail_payload, ensure_ascii=False)
