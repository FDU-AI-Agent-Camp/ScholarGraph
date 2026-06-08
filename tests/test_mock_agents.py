"""Tests for mock agents (LLM_MODE=mock pipeline path)."""

from __future__ import annotations

import pytest
from backend.agents.classifier import classify
from backend.agents.extractor import extract
from backend.config import get_settings
from backend.llm.client import reset_llm_client_cache
from backend.schemas.paradigm import Paradigm


@pytest.fixture(autouse=True)
def _mock_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "mock")
    get_settings.cache_clear()
    reset_llm_client_cache()


@pytest.mark.asyncio
async def test_mock_classify_stem_from_ml_keywords() -> None:
    result = await classify(
        "Abstract: machine learning crystal property prediction with benchmark datasets.",
    )
    assert result.classification.paradigm == Paradigm.STEM
    assert result.classification.confidence >= 0.7


@pytest.mark.asyncio
async def test_mock_classify_hss_from_chinese_keywords() -> None:
    result = await classify("夏尔巴人父系历史与分子考古民族史研究。")
    assert result.classification.paradigm == Paradigm.HSS


@pytest.mark.asyncio
async def test_mock_extract_hss_returns_fixture_graph() -> None:
    graph = (await extract("任意全文", Paradigm.HSS)).graph
    assert graph.paradigm == Paradigm.HSS
    assert any(node.type == "Thesis" for node in graph.nodes)


@pytest.mark.asyncio
async def test_mock_extract_stem_returns_verification_chain() -> None:
    graph = (await extract("任意全文", Paradigm.STEM)).graph
    assert graph.paradigm == Paradigm.STEM
    types = {node.type for node in graph.nodes}
    assert "Method" in types
    assert "Evidence" in types


@pytest.mark.asyncio
async def test_mock_classify_empty_input_defaults_hss() -> None:
    result = await classify("   ")
    assert result.classification.paradigm == Paradigm.HSS
    assert result.classification.reason.strip()


@pytest.mark.asyncio
async def test_mock_extract_unknown_paradigm_still_returns_nodes() -> None:
    graph = (await extract("text", Paradigm.HSS)).graph
    assert graph.nodes
    assert graph.edges is not None
