"""Phase F.2.1 acceptance tests (X1–X8): LLM structured extract main path."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE
from backend.agents.extract_llm import (
    PROMPTS_DIR,
    build_user_payload,
    extract_with_llm,
    load_extract_prompt,
)
from backend.agents.extract_types import ExtractResult
from backend.agents.extractor import extract
from backend.config import get_settings
from backend.llm.client import LlmClient, reset_llm_client_cache
from backend.schemas.graph import GraphNode, UnifiedPaperGraph
from backend.schemas.ingest_head import IngestHead
from backend.schemas.paradigm import Paradigm


@pytest.fixture
def live_extract_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("EXTRACT_LLM_ENABLED", "true")
    monkeypatch.setenv("EXTRACT_HEURISTIC_FALLBACK", "true")
    monkeypatch.setenv("EXTRACT_MAX_INPUT_CHARS", "100")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "99")
    get_settings.cache_clear()
    reset_llm_client_cache()


# ── X1: live 调用 with_structured_output ─────────────────────────────────────


@pytest.mark.asyncio
async def test_x1_live_extract_invokes_with_structured_output(live_extract_env) -> None:
    _ = live_extract_env
    llm_graph = UnifiedPaperGraph(
        paper_id="ignored",
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="论点", type="Thesis")],
        edges=[],
    )
    structured_runnable = MagicMock()
    structured_runnable.ainvoke = AsyncMock(return_value=llm_graph)
    chat = MagicMock()
    chat.with_structured_output.return_value = structured_runnable

    client = LlmClient()
    client._chat = chat
    client._fallback_chat = None

    graph = await extract_with_llm(
        "标题：测试\n本文认为……",
        Paradigm.HSS,
        paper_id="paper-x1",
        llm_client=client,
    )

    chat.with_structured_output.assert_called_once_with(UnifiedPaperGraph)
    structured_runnable.ainvoke.assert_awaited_once()
    assert graph.paper_id == "paper-x1"

    get_settings.cache_clear()
    reset_llm_client_cache()


# ── X2: 范式分支 prompt ──────────────────────────────────────────────────────


def test_x2_load_extract_prompt_hss_and_stem() -> None:
    hss_prompt = load_extract_prompt(Paradigm.HSS)
    stem_prompt = load_extract_prompt(Paradigm.STEM)

    assert "HSS" in hss_prompt or "humanities" in hss_prompt.lower()
    assert "Thesis" in hss_prompt
    assert "STEM" in stem_prompt or "research problem" in stem_prompt.lower()
    assert "ResearchQuestion" in stem_prompt or "Method" in stem_prompt
    assert (PROMPTS_DIR / "extract_hss.md").is_file()
    assert (PROMPTS_DIR / "extract_stem.md").is_file()


@pytest.mark.asyncio
async def test_x2_extract_with_llm_uses_paradigm_prompt(live_extract_env) -> None:
    _ = live_extract_env
    captured: dict[str, str] = {}

    async def _capture_invoke(_client, *, system_prompt, user_content, use_fallback_model):
        captured["system_prompt"] = system_prompt
        captured["use_fallback"] = str(use_fallback_model)
        return UnifiedPaperGraph(
            paper_id="p",
            paradigm=Paradigm.STEM,
            nodes=[GraphNode(id="n1", label="m", type="Method")],
            edges=[],
        )

    with patch("backend.agents.extract_llm._invoke_structured", side_effect=_capture_invoke):
        await extract_with_llm("body", Paradigm.STEM, paper_id="p-stem")

    assert "STEM" in captured["system_prompt"]
    assert "ResearchQuestion" in captured["system_prompt"] or "Method" in captured["system_prompt"]


# ── X3: UnifiedPaperGraph 校验失败 → fallback ────────────────────────────────


@pytest.mark.asyncio
async def test_x3_dangling_edge_validation_triggers_fallback(live_extract_env) -> None:
    _ = live_extract_env

    with patch(
        "backend.agents.extract_llm._invoke_structured",
        new=AsyncMock(side_effect=ValueError("Graph edge e1 references missing node.")),
    ):
        result = await extract("标题：测试", Paradigm.HSS, paper_id="paper-x3")

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings
    assert any(node.type == "Thesis" for node in result.graph.nodes)


@pytest.mark.asyncio
async def test_x3_forbidden_node_type_triggers_fallback(live_extract_env) -> None:
    _ = live_extract_env

    with patch(
        "backend.agents.extract_llm._invoke_structured",
        new=AsyncMock(
            side_effect=ValueError("HSS graph contains forbidden node types: ['Metric']"),
        ),
    ):
        result = await extract("标题：测试", Paradigm.HSS, paper_id="paper-x3b")

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings


# ── X4: paper_id / paradigm 由服务层注入 ─────────────────────────────────────


@pytest.mark.asyncio
async def test_x4_service_overrides_llm_paper_id_and_paradigm(live_extract_env) -> None:
    _ = live_extract_env
    llm_graph = UnifiedPaperGraph(
        paper_id="llm-wrong-id",
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="论点", type="Thesis")],
        edges=[],
    )

    with patch("backend.agents.extractor.extract_with_llm", new=AsyncMock(return_value=llm_graph)):
        result = await extract("标题：测试", Paradigm.HSS, paper_id="canonical-id")

    assert result.graph.paper_id == "canonical-id"
    assert result.graph.paradigm == Paradigm.HSS


# ── X5: 输入截断 + 日志 ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_x5_truncation_respects_extract_max_input_chars(live_extract_env) -> None:
    _ = live_extract_env
    long_text = "x" * 250

    payload = json.loads(
        build_user_payload(
            full_text=long_text,
            paradigm=Paradigm.HSS,
            paper_id="p5",
            title="T",
            head_context=None,
            max_chars=get_settings().extract_max_input_chars,
        ),
    )

    assert payload["truncated"] is True
    assert len(payload["full_text"]) == 100


@pytest.mark.asyncio
async def test_x5_truncation_emits_warning_log(live_extract_env, caplog: pytest.LogCaptureFixture) -> None:
    _ = live_extract_env
    llm_graph = UnifiedPaperGraph(
        paper_id="p",
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="t", type="Thesis")],
        edges=[],
    )

    with (
        patch("backend.agents.extract_llm._invoke_structured", new=AsyncMock(return_value=llm_graph)),
        caplog.at_level("WARNING"),
    ):
        await extract_with_llm("y" * 200, Paradigm.HSS, paper_id="paper-x5")

    assert any("extract_input_truncated" in record.message for record in caplog.records)


# ── X6: IngestHead 注入 user message ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_x6_head_store_metadata_in_user_payload(live_extract_env, tmp_path, monkeypatch) -> None:
    _ = live_extract_env
    monkeypatch.setenv("GRAPH_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()

    from backend.graph.head_store import HeadStore

    paper_id = "paper-x6"
    HeadStore(base_dir=tmp_path).save(
        paper_id,
        merged=IngestHead(title="Refined Title", abstract="Refined abstract body"),
        classifier_input="Title: Refined Title",
    )

    payload = json.loads(
        build_user_payload(
            full_text="正文",
            paradigm=Paradigm.HSS,
            paper_id=paper_id,
            title="T",
            head_context="Refined Title\n\nRefined abstract body",
            max_chars=500,
        ),
    )

    assert "document_head" in payload
    assert "Refined abstract" in payload["document_head"]

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_x6_extractor_resolves_head_from_head_store(live_extract_env, tmp_path, monkeypatch) -> None:
    _ = live_extract_env
    monkeypatch.setenv("GRAPH_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()

    from backend.agents.extractor import _resolve_head_context
    from backend.graph.head_store import HeadStore

    paper_id = "paper-x6b"
    HeadStore(base_dir=tmp_path).save(
        paper_id,
        merged=IngestHead(title="Disk Head", abstract="Disk abstract"),
        classifier_input="Title: Disk Head",
    )

    context = _resolve_head_context(paper_id)

    assert context is not None
    assert "Disk Head" in context
    assert "Disk abstract" in context

    get_settings.cache_clear()


# ── X7: 主备模型重试 ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_x7_primary_failure_retries_fallback_chat(live_extract_env) -> None:
    _ = live_extract_env
    valid_graph = UnifiedPaperGraph(
        paper_id="p7",
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="t", type="Thesis")],
        edges=[],
    )

    primary_runnable = MagicMock()
    primary_runnable.ainvoke = AsyncMock(side_effect=RuntimeError("primary down"))
    fallback_runnable = MagicMock()
    fallback_runnable.ainvoke = AsyncMock(return_value=valid_graph)

    primary_chat = MagicMock()
    primary_chat.with_structured_output.return_value = primary_runnable
    fallback_chat = MagicMock()
    fallback_chat.with_structured_output.return_value = fallback_runnable

    client = LlmClient()
    client._chat = primary_chat
    client._fallback_chat = fallback_chat

    graph = await extract_with_llm("body", Paradigm.HSS, paper_id="p7", llm_client=client)

    assert graph.nodes
    primary_runnable.ainvoke.assert_awaited_once()
    fallback_runnable.ainvoke.assert_awaited_once()

    get_settings.cache_clear()
    reset_llm_client_cache()


def test_x7_llm_client_reads_llm_timeout_seconds_from_settings(live_extract_env) -> None:
    _ = live_extract_env
    client = LlmClient()
    assert client._settings.llm_timeout_seconds == 99
    assert client.is_mock is False

    get_settings.cache_clear()
    reset_llm_client_cache()


# ── X8: mock 模式不变 ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_x8_mock_mode_skips_llm_and_returns_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "mock")
    get_settings.cache_clear()

    with patch("backend.agents.extractor.extract_with_llm", new=AsyncMock()) as llm_mock:
        result = await extract("任意全文", Paradigm.HSS, paper_id="mock-x8")

    llm_mock.assert_not_awaited()
    assert isinstance(result, ExtractResult)
    assert result.warnings == []
    assert result.graph.paradigm == Paradigm.HSS
    assert any(node.type == "Thesis" for node in result.graph.nodes)

    get_settings.cache_clear()
