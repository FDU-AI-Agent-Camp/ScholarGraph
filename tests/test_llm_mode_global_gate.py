"""G.4 cross-module gate: LLM_MODE=mock must skip live LLM for classify / extract / head merge."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from backend.agents.classifier import classify
from backend.agents.extractor import extract
from backend.config import Settings, get_settings
from backend.ingest.head_candidates import HeadCandidate
from backend.ingest.head_merge import merge_head_candidates
from backend.llm.client import reset_llm_client_cache
from backend.schemas.paradigm import Paradigm

STEM_SAMPLE = (
    "Title: Agent framework benchmark. We evaluate the model on datasets with accuracy, "
    "F1 metrics, baselines, and ablation experiments."
)
HSS_SAMPLE = "标题：近代口岸制度研究\n本文认为通商口岸体现制度路径依赖。"


@pytest.fixture
def mock_mode_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setenv("CLASSIFIER_LLM_ENABLED", "true")
    monkeypatch.setenv("EXTRACT_LLM_ENABLED", "true")
    monkeypatch.setenv("INGEST_HEAD_LLM_ENABLED", "true")
    get_settings.cache_clear()
    reset_llm_client_cache()


@pytest.mark.asyncio
async def test_g4_global_mock_classify_skips_classify_with_llm(mock_mode_env: None) -> None:
    _ = mock_mode_env
    with patch("backend.agents.classifier.classify_with_llm", new=AsyncMock()) as llm_mock:
        result = await classify(STEM_SAMPLE)

    llm_mock.assert_not_awaited()
    assert result.warnings == []


@pytest.mark.asyncio
async def test_g4_global_mock_extract_skips_extract_with_llm(mock_mode_env: None) -> None:
    _ = mock_mode_env
    with patch("backend.agents.extractor.extract_with_llm", new=AsyncMock()) as llm_mock:
        result = await extract(HSS_SAMPLE, Paradigm.HSS, paper_id="g4-mock-extract")

    llm_mock.assert_not_awaited()
    assert result.warnings == []
    assert result.graph.nodes


@pytest.mark.asyncio
async def test_g4_global_mock_head_merge_skips_merge_with_llm() -> None:
    settings = Settings(_env_file=None, llm_mode="mock", ingest_head_llm_enabled=True)
    snippets = HeadCandidate(title="Snippet", source="pymupdf")
    path_b = HeadCandidate(title="Path B", source="grobid")

    with patch("backend.ingest.head_merge.merge_with_llm", new=AsyncMock()) as llm_mock:
        merged = await merge_head_candidates(snippets, path_b, is_short=False, settings=settings)

    llm_mock.assert_not_awaited()
    assert merged.title == "Path B"


def test_g4_env_example_documents_classifier_switches_with_semantics() -> None:
    from pathlib import Path

    text = Path(__file__).resolve().parents[1] / ".env.example"
    content = text.read_text(encoding="utf-8")
    assert "CLASSIFIER_LLM_ENABLED" in content
    assert "CLASSIFIER_HEURISTIC_FALLBACK" in content
    assert "范式分类（Phase G）" in content
