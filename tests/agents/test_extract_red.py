# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""
Phase F 红灯测试（边界情形）

运行：uv run pytest -m red tests/agents/test_extract_red.py -rx
默认 CI：uv run pytest -m "not red"
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE
from backend.agents.extractor import extract
from backend.config import get_settings
from backend.graph.workflow import run_paper_pipeline
from backend.llm.client import reset_llm_client_cache
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.schemas.paradigm import Paradigm
from backend.services.agent_service import AgentService
from backend.services.errors import ServiceError
from backend.services.paper_service import get_paper_service
from tests.conftest import mock_pipeline_node_services
from tests.ingest.conftest import CORPUS_HSS, CORPUS_PAPER_IDS, CORPUS_STEM


@pytest.fixture
def live_extract_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("EXTRACT_LLM_ENABLED", "true")
    monkeypatch.setenv("EXTRACT_HEURISTIC_FALLBACK", "true")
    get_settings.cache_clear()
    reset_llm_client_cache()


@pytest.mark.red
@pytest.mark.asyncio
async def test_red_extract_empty_full_text_raises(live_extract_env) -> None:
    _ = live_extract_env
    with pytest.raises(ValueError, match="non-empty"):
        await extract("", Paradigm.HSS)


@pytest.mark.red
@pytest.mark.asyncio
async def test_red_extract_whitespace_only_raises(live_extract_env) -> None:
    _ = live_extract_env
    with pytest.raises(ValueError, match="non-empty"):
        await extract("   \n\t  ", Paradigm.HSS)


@pytest.mark.red
@pytest.mark.asyncio
async def test_red_extract_llm_empty_nodes_triggers_fallback(live_extract_env) -> None:
    _ = live_extract_env
    empty_graph = UnifiedPaperGraph(
        paper_id="p",
        paradigm=Paradigm.HSS,
        nodes=[],
        edges=[],
    )
    with patch(
        "backend.agents.extract_llm._invoke_structured",
        new=AsyncMock(return_value=empty_graph),
    ):
        result = await extract("标题：测试", Paradigm.HSS, paper_id="paper-empty")

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings
    assert result.graph.nodes


@pytest.mark.red
@pytest.mark.asyncio
async def test_red_extract_llm_wrong_paradigm_triggers_fallback(live_extract_env) -> None:
    _ = live_extract_env
    wrong_graph = UnifiedPaperGraph(
        paper_id="p",
        paradigm=Paradigm.STEM,
        nodes=[GraphNode(id="n1", label="m", type="Method")],
        edges=[],
    )
    with patch(
        "backend.agents.extract_llm._invoke_structured",
        new=AsyncMock(return_value=wrong_graph),
    ):
        result = await extract("标题：测试", Paradigm.HSS, paper_id="paper-mismatch")

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings
    assert result.graph.paradigm == Paradigm.HSS


@pytest.mark.red
@pytest.mark.asyncio
async def test_red_extract_fallback_disabled_fails_pipeline(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from backend.schemas.paper import PaperDetail

    paper_id = "red-extract-fail-001"
    pdf_path = tmp_path / "red.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% red test")
    now = datetime.now(UTC)
    get_paper_service()._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="red extract fail",
        status=PaperStatus.PENDING,
        created_at=now,
        updated_at=now,
    )
    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["agent"].extract_graph = AsyncMock(
            side_effect=ServiceError("PIPELINE_FAILED", "图谱 LLM 抽取失败: simulated"),
        )
        final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("failed") is True
    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.FAILED
    assert status.failed_during == PipelineStage.EXTRACTING


@pytest.mark.red
@pytest.mark.asyncio
async def test_red_agent_service_fallback_disabled_maps_pipeline_failed(live_extract_env, monkeypatch) -> None:
    _ = live_extract_env
    monkeypatch.setenv("EXTRACT_HEURISTIC_FALLBACK", "false")
    get_settings.cache_clear()

    with (
        patch(
            "backend.agents.extractor.extract_with_llm",
            new=AsyncMock(side_effect=RuntimeError("llm down")),
        ),
        pytest.raises(ServiceError) as err,
    ):
        await AgentService().extract_graph("body", Paradigm.HSS, paper_id="pid")

    assert err.value.code == "PIPELINE_FAILED"


@pytest.mark.red
@pytest.mark.parametrize(
    ("pdf_path", "paper_id"),
    ((CORPUS_STEM, "stem-001"), (CORPUS_HSS, "hss-001")),
    ids=[pid for pid in CORPUS_PAPER_IDS if pid != "hss-002"],
)
@pytest.mark.asyncio
async def test_red_corpus_extract_produces_valid_graph_with_llm_or_fallback(
    pdf_path,
    paper_id: str,
    live_extract_env,
) -> None:
    """Corpus PDF → ingest full_text → extract (LLM or fallback) yields valid graph."""
    from backend.ingest.pdf import ingest_pdf

    _ = live_extract_env
    if not pdf_path.is_file():
        pytest.skip(f"微语料 PDF 未就位: {pdf_path}")

    paradigm = Paradigm.STEM if paper_id == "stem-001" else Paradigm.HSS
    full_text = (await ingest_pdf(pdf_path, paper_id=paper_id))["full_text"]

    with patch(
        "backend.agents.extractor.extract_with_llm",
        new=AsyncMock(side_effect=RuntimeError("no live llm in red corpus gate")),
    ):
        result = await extract(full_text, paradigm, paper_id=paper_id)

    assert result.graph.paper_id == paper_id
    assert result.graph.nodes
    assert result.graph.paradigm == paradigm


@pytest.mark.red
@pytest.mark.asyncio
async def test_red_missing_llm_api_key_triggers_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.delenv("SCHOLARGRAPH_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("EXTRACT_LLM_ENABLED", "true")
    monkeypatch.setenv("EXTRACT_HEURISTIC_FALLBACK", "true")
    get_settings.cache_clear()
    reset_llm_client_cache()

    result = await extract("标题：测试\n本文认为……", Paradigm.HSS, paper_id="paper-no-key")

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings
    assert result.graph.nodes

    get_settings.cache_clear()
    reset_llm_client_cache()


@pytest.mark.red
@pytest.mark.asyncio
async def test_red_missing_extract_prompt_triggers_fallback(live_extract_env) -> None:
    _ = live_extract_env

    with patch(
        "backend.agents.extract_llm.load_extract_prompt",
        side_effect=FileNotFoundError("Missing extract prompt"),
    ):
        result = await extract("标题：测试", Paradigm.HSS, paper_id="paper-no-prompt")

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings


@pytest.mark.red
@pytest.mark.asyncio
async def test_red_primary_and_fallback_llm_both_fail(live_extract_env) -> None:
    _ = live_extract_env

    with patch(
        "backend.agents.extract_llm._invoke_structured",
        new=AsyncMock(side_effect=RuntimeError("both models down")),
    ):
        result = await extract("标题：测试", Paradigm.STEM, paper_id="paper-both-fail")

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings
    assert result.graph.paradigm == Paradigm.STEM


@pytest.mark.red
@pytest.mark.asyncio
async def test_red_extract_max_input_chars_zero_keeps_full_text(live_extract_env, monkeypatch) -> None:
    _ = live_extract_env
    monkeypatch.setenv("EXTRACT_MAX_INPUT_CHARS", "0")
    get_settings.cache_clear()

    long_text = "z" * 500
    captured: dict[str, str] = {}

    async def _capture_invoke(_client, *, system_prompt, user_content, use_fallback_model):
        captured["user_content"] = user_content
        return UnifiedPaperGraph(
            paper_id="p",
            paradigm=Paradigm.HSS,
            nodes=[GraphNode(id="n1", label="t", type="Thesis")],
            edges=[GraphEdge(id="e1", source="n1", target="n1", label="REF", type="REF")],
        )

    with patch("backend.agents.extract_llm._invoke_structured", side_effect=_capture_invoke):
        result = await extract(long_text, Paradigm.HSS, paper_id="paper-no-trunc")

    payload = __import__("json").loads(captured["user_content"])
    assert payload["truncated"] is False
    assert len(payload["full_text"]) == 500
    assert result.warnings == []

    get_settings.cache_clear()


@pytest.mark.red
@pytest.mark.asyncio
async def test_red_empty_edges_triggers_fallback(live_extract_env) -> None:
    _ = live_extract_env
    no_edges = UnifiedPaperGraph(
        paper_id="p",
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="论点", type="Thesis")],
        edges=[],
    )
    with patch(
        "backend.agents.extract_llm._invoke_structured",
        new=AsyncMock(return_value=no_edges),
    ):
        result = await extract("标题：测试", Paradigm.HSS, paper_id="paper-red-empty-edges")

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings
    assert result.graph.edges


@pytest.mark.red
@pytest.mark.asyncio
async def test_red_pydantic_validation_error_triggers_fallback(live_extract_env) -> None:
    _ = live_extract_env

    with patch(
        "backend.agents.extract_llm._invoke_structured",
        new=AsyncMock(return_value={"paper_id": "", "paradigm": "STEM", "nodes": []}),
    ):
        result = await extract("标题：测试", Paradigm.STEM, paper_id="paper-red-pydantic")

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings
    assert result.graph.paradigm == Paradigm.STEM


@pytest.mark.red
@pytest.mark.asyncio
async def test_red_extract_llm_disabled_uses_heuristic_warning(live_extract_env, monkeypatch) -> None:
    _ = live_extract_env
    monkeypatch.setenv("EXTRACT_LLM_ENABLED", "false")
    get_settings.cache_clear()

    with patch("backend.agents.extractor.extract_with_llm", new=AsyncMock()) as llm_mock:
        result = await extract("标题：测试", Paradigm.HSS, paper_id="paper-red-llm-off")

    llm_mock.assert_not_awaited()
    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings

    get_settings.cache_clear()


@pytest.mark.red
@pytest.mark.asyncio
async def test_red_hss_forbidden_stem_node_type_triggers_fallback(live_extract_env) -> None:
    _ = live_extract_env

    with patch(
        "backend.agents.extract_llm._invoke_structured",
        new=AsyncMock(side_effect=ValueError("HSS graph contains forbidden node types: ['Metric']")),
    ):
        result = await extract("标题：测试", Paradigm.HSS, paper_id="paper-forbidden-type")

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings
