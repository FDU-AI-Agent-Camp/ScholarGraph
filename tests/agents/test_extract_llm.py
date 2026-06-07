"""Phase F: LLM extract with heuristic fallback."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE
from backend.agents.extract_llm import build_user_payload, truncate_full_text
from backend.agents.extract_types import ExtractResult
from backend.agents.extractor import extract
from backend.config import get_settings
from backend.llm.client import reset_llm_client_cache
from backend.schemas.paradigm import Paradigm
from tests.agents.conftest import minimal_valid_llm_graph


@pytest.fixture
def live_extract_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("EXTRACT_LLM_ENABLED", "true")
    monkeypatch.setenv("EXTRACT_HEURISTIC_FALLBACK", "true")
    get_settings.cache_clear()
    reset_llm_client_cache()


def test_truncate_full_text_reports_truncation() -> None:
    text, truncated = truncate_full_text("abcdef", max_chars=3)
    assert text == "abc"
    assert truncated is True


def test_build_user_payload_includes_document_head() -> None:
    payload = build_user_payload(
        full_text="body",
        paradigm=Paradigm.HSS,
        paper_id="p1",
        title="T",
        head_context="Abstract: x",
        max_chars=100,
    )
    assert "document_head" in payload
    assert "Abstract: x" in payload


@pytest.mark.asyncio
async def test_live_llm_success_returns_graph_without_warnings(live_extract_env) -> None:
    _ = live_extract_env
    llm_graph = minimal_valid_llm_graph(summary="llm")

    with patch("backend.agents.extractor.extract_with_llm", new=AsyncMock(return_value=llm_graph)):
        result = await extract("标题：测试\n本文认为……", Paradigm.HSS, paper_id="paper-1")

    assert isinstance(result, ExtractResult)
    assert result.warnings == []
    assert result.graph.paper_id == "paper-1"
    assert result.graph.nodes[0].label == "core"


@pytest.mark.asyncio
async def test_live_llm_failure_falls_back_to_heuristic_with_warning(live_extract_env) -> None:
    _ = live_extract_env

    with patch(
        "backend.agents.extractor.extract_with_llm",
        new=AsyncMock(side_effect=RuntimeError("structured output failed")),
    ):
        result = await extract(
            "标题：近代口岸研究\n本文认为通商口岸体现制度路径依赖。",
            Paradigm.HSS,
            paper_id="paper-2",
        )

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings
    assert result.graph.paper_id == "paper-2"
    assert any(node.type == "Thesis" for node in result.graph.nodes)
    assert "启发式 fallback" in (result.graph.summary or "")


@pytest.mark.asyncio
async def test_extract_llm_disabled_uses_heuristic_with_warning(live_extract_env, monkeypatch) -> None:
    _ = live_extract_env
    monkeypatch.setenv("EXTRACT_LLM_ENABLED", "false")
    get_settings.cache_clear()

    with patch("backend.agents.extractor.extract_with_llm", new=AsyncMock()) as llm_mock:
        result = await extract("标题：测试", Paradigm.STEM, paper_id="paper-3")

    llm_mock.assert_not_awaited()
    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings
    assert result.graph.paradigm == Paradigm.STEM


@pytest.mark.asyncio
async def test_mock_mode_returns_fixture_without_warnings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "mock")
    get_settings.cache_clear()

    result = await extract("任意全文", Paradigm.HSS, paper_id="mock-paper")

    assert result.warnings == []
    assert result.graph.paradigm == Paradigm.HSS
    assert result.graph.nodes


@pytest.mark.asyncio
async def test_live_empty_full_text_raises_value_error(live_extract_env) -> None:
    _ = live_extract_env
    with pytest.raises(ValueError, match="non-empty"):
        await extract("  ", Paradigm.STEM)


@pytest.mark.asyncio
async def test_fallback_disabled_raises_service_error(live_extract_env, monkeypatch) -> None:
    _ = live_extract_env
    monkeypatch.setenv("EXTRACT_HEURISTIC_FALLBACK", "false")
    get_settings.cache_clear()

    with (
        patch(
            "backend.agents.extractor.extract_with_llm",
            new=AsyncMock(side_effect=ValueError("bad json")),
        ),
        pytest.raises(Exception, match="图谱 LLM 抽取失败"),
    ):
        await extract("标题：测试", Paradigm.HSS, paper_id="paper-4")
