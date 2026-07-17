# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Diagnose extract heuristic fallback when paradigm classify succeeds (Phase G + F).

Classify (``ParadigmClassification``) and extract (``UnifiedPaperGraph``) are independent:
classify may succeed without ``classify_warnings`` while extract still emits
``extract_heuristic_fallback``. Root cause is logged as ``extract_llm_fallback`` or
``extract_llm_disabled`` (reason in log extra), not exposed in API status.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from backend.agents.classifier_types import ClassifyResult
from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE
from backend.agents.extractor import extract
from backend.config import get_settings
from backend.llm.client import reset_llm_client_cache
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm, ParadigmClassification

STEM_CLASSIFIER_INPUT = (
    "Title: Agent framework benchmark. We evaluate the model on datasets with accuracy, "
    "F1 metrics, baselines, and ablation experiments."
)
STEM_FULL_TEXT = STEM_CLASSIFIER_INPUT + "\n\nWe report F1 and accuracy against baselines."


@pytest.fixture
def live_both_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("CLASSIFIER_LLM_ENABLED", "true")
    monkeypatch.setenv("CLASSIFIER_HEURISTIC_FALLBACK", "true")
    monkeypatch.setenv("EXTRACT_LLM_ENABLED", "true")
    monkeypatch.setenv("EXTRACT_HEURISTIC_FALLBACK", "true")
    get_settings.cache_clear()
    reset_llm_client_cache()


def _classify_llm_success() -> ClassifyResult:
    return ClassifyResult(
        classification=ParadigmClassification(
            paradigm=Paradigm.STEM,
            confidence=0.93,
            reason="Quantitative benchmark with datasets and metrics.",
        ),
        warnings=[],
    )


@pytest.mark.asyncio
async def test_classify_success_and_extract_fallback_are_independent(live_both_llm_env: None) -> None:
    """Classify LLM 主路径成功时，extract LLM 失败仍应仅写 extract_warnings。"""
    _ = live_both_llm_env
    from backend.agents.classifier import classify

    with patch(
        "backend.agents.classifier.classify_with_llm",
        new=AsyncMock(return_value=_classify_llm_success().classification),
    ):
        classify_result = await classify(STEM_CLASSIFIER_INPUT)

    assert classify_result.warnings == []

    with patch(
        "backend.agents.extractor.extract_with_llm",
        new=AsyncMock(side_effect=RuntimeError("structured output failed")),
    ):
        extract_result = await extract(STEM_FULL_TEXT, Paradigm.STEM, paper_id="diag-indep")

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in extract_result.warnings
    assert classify_result.warnings == []


@pytest.mark.asyncio
async def test_extract_llm_disabled_while_classify_enabled(
    live_both_llm_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EXTRACT_LLM_ENABLED=false 时 classify 仍可走 LLM，extract 必 fallback。"""
    _ = live_both_llm_env
    from backend.agents.classifier import classify

    monkeypatch.setenv("EXTRACT_LLM_ENABLED", "false")
    get_settings.cache_clear()
    reset_llm_client_cache()

    with patch(
        "backend.agents.classifier.classify_with_llm",
        new=AsyncMock(return_value=_classify_llm_success().classification),
    ):
        classify_result = await classify(STEM_CLASSIFIER_INPUT)

    assert classify_result.warnings == []

    with patch("backend.agents.extractor.extract_with_llm", new=AsyncMock()) as extract_llm_mock:
        extract_result = await extract(STEM_FULL_TEXT, Paradigm.STEM, paper_id="diag-extract-off")

    extract_llm_mock.assert_not_awaited()
    assert EXTRACT_HEURISTIC_FALLBACK_CODE in extract_result.warnings


@pytest.mark.parametrize(
    ("side_effect", "reason_substring"),
    [
        (RuntimeError("with_structured_output failed"), "with_structured_output failed"),
        (TimeoutError("api timeout"), "api timeout"),
        (ValueError("LLM graph has no nodes."), "no nodes"),
        (ValueError("LLM graph has no edges."), "no edges"),
        (ValueError("LLM graph paradigm HSS != expected STEM."), "paradigm"),
    ],
)
@pytest.mark.asyncio
async def test_extract_fallback_logs_reason_while_classify_clean(
    live_both_llm_env: None,
    caplog: pytest.LogCaptureFixture,
    side_effect: Exception,
    reason_substring: str,
) -> None:
    """extract_llm_fallback 日志 extra.reason 应含失败根因（API 仅返回机器码）。"""
    _ = live_both_llm_env
    caplog.set_level("WARNING", logger="backend.agents.extractor")

    with patch(
        "backend.agents.extractor.extract_with_llm",
        new=AsyncMock(side_effect=side_effect),
    ):
        result = await extract(STEM_FULL_TEXT, Paradigm.STEM, paper_id="diag-log")

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings
    records = [r for r in caplog.records if r.getMessage() == "extract_llm_fallback"]
    assert len(records) == 1
    assert reason_substring in str(getattr(records[0], "reason", ""))


@pytest.mark.asyncio
async def test_extract_llm_disabled_logs_extract_llm_disabled(
    live_both_llm_env: None,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _ = live_both_llm_env
    monkeypatch.setenv("EXTRACT_LLM_ENABLED", "false")
    get_settings.cache_clear()
    reset_llm_client_cache()
    caplog.set_level("WARNING", logger="backend.agents.extractor")

    with patch("backend.agents.extractor.extract_with_llm", new=AsyncMock()):
        await extract(STEM_FULL_TEXT, Paradigm.STEM, paper_id="diag-disabled-log")

    disabled_records = [r for r in caplog.records if r.getMessage() == "extract_llm_disabled"]
    fallback_records = [r for r in caplog.records if r.getMessage() == "extract_llm_fallback"]
    assert len(disabled_records) == 1
    assert len(fallback_records) == 1
    assert "extract_llm_disabled" in str(getattr(fallback_records[0], "reason", ""))


@pytest.mark.asyncio
async def test_empty_nodes_from_llm_triggers_fallback_not_classify_issue(live_both_llm_env: None) -> None:
    """UnifiedPaperGraph 校验失败（空 nodes）是 extract 独有路径，与 classify 无关。"""
    _ = live_both_llm_env
    empty_graph = UnifiedPaperGraph(
        paper_id="p",
        paradigm=Paradigm.STEM,
        nodes=[],
        edges=[],
    )
    with patch(
        "backend.agents.extract_llm._invoke_structured",
        new=AsyncMock(return_value=empty_graph),
    ):
        result = await extract(STEM_FULL_TEXT, Paradigm.STEM, paper_id="diag-empty-nodes")

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings
    assert result.graph.nodes


@pytest.mark.asyncio
async def test_paradigm_field_mismatch_coerced_when_node_types_match(live_both_llm_env: None) -> None:
    """LLM 返回错误 paradigm 字段但节点类型正确时，应校正而非 fallback。"""
    _ = live_both_llm_env
    mislabeled = UnifiedPaperGraph.model_construct(
        paper_id="p",
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="GNN method", type="Method")],
        edges=[GraphEdge(id="e1", source="n1", target="n1", label="RELATES_TO", type="RELATES_TO")],
    )
    with patch(
        "backend.agents.extract_llm._invoke_structured",
        new=AsyncMock(return_value=mislabeled),
    ):
        result = await extract(STEM_FULL_TEXT, Paradigm.STEM, paper_id="diag-paradigm-coerce")

    from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE

    assert EXTRACT_HEURISTIC_FALLBACK_CODE not in result.warnings
    assert result.graph.paradigm == Paradigm.STEM


@pytest.mark.asyncio
async def test_wrong_paradigm_with_incompatible_nodes_still_fallbacks(live_both_llm_env: None) -> None:
    _ = live_both_llm_env
    wrong_paradigm = UnifiedPaperGraph(
        paper_id="p",
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="论点", type="Thesis")],
        edges=[GraphEdge(id="e1", source="n1", target="n1", label="REF", type="REF")],
    )
    with patch(
        "backend.agents.extract_llm._invoke_structured",
        new=AsyncMock(return_value=wrong_paradigm),
    ):
        result = await extract(STEM_FULL_TEXT, Paradigm.STEM, paper_id="diag-paradigm-mismatch")

    from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings


@pytest.mark.asyncio
async def test_extract_llm_logs_primary_and_fallback_attempt_failures(
    live_both_llm_env: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """主/备模型均失败时 extract_llm 会各打一条 attempt failed，随后 fallback。"""
    _ = live_both_llm_env
    caplog.set_level("WARNING", logger="backend.agents.extract_llm")

    with patch(
        "backend.agents.extract_llm._invoke_structured",
        new=AsyncMock(side_effect=RuntimeError("both models down")),
    ):
        result = await extract(STEM_FULL_TEXT, Paradigm.STEM, paper_id="diag-dual-fail")

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings
    attempt_logs = [r for r in caplog.records if "extract_llm attempt failed" in r.getMessage()]
    assert len(attempt_logs) >= 1
