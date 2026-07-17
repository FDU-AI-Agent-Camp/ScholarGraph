# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""
Phase G G.0–G.6 红灯：产品决策 / 架构 / OpenAPI / fixtures 边界。

运行：uv run pytest -m red tests/test_phase_g_g0_g6_red.py -rx
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from backend.agents.classifier import classify
from backend.agents.classifier_constants import (
    CLASSIFIER_HEURISTIC_FALLBACK_CODE,
    CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE,
)
from backend.agents.classifier_llm import classify_with_llm
from backend.config import get_settings
from backend.llm.client import LlmClient, reset_llm_client_cache
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.errors import ServiceError

pytestmark = pytest.mark.red

REPO_ROOT = Path(__file__).resolve().parents[1]
OPENAPI = REPO_ROOT / "docs" / "api" / "openapi.yaml"
FIXTURES_DIR = REPO_ROOT / "docs" / "api" / "fixtures"

STEM_SAMPLE = (
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


@pytest.mark.asyncio
async def test_red_g0_live_llm_success_must_not_emit_fallback_warning(live_classify_env: None) -> None:
    """G.0: LLM 主路径成功时不得写 classifier_heuristic_fallback。"""
    _ = live_classify_env
    expected = ParadigmClassification(
        paradigm=Paradigm.STEM,
        confidence=0.9,
        reason="Benchmark paper.",
    )
    with patch(
        "backend.agents.classifier.classify_with_llm",
        new=AsyncMock(return_value=expected),
    ):
        result = await classify(STEM_SAMPLE)

    assert result.warnings == []
    assert CLASSIFIER_HEURISTIC_FALLBACK_CODE not in result.warnings


@pytest.mark.asyncio
async def test_red_g0_live_llm_success_must_not_call_heuristic_primary(live_classify_env: None) -> None:
    """G.0: 启发式不得作为 live 默认主路径。"""
    _ = live_classify_env
    expected = ParadigmClassification(
        paradigm=Paradigm.STEM,
        confidence=0.9,
        reason="Benchmark paper.",
    )
    with (
        patch(
            "backend.agents.classifier.classify_with_llm",
            new=AsyncMock(return_value=expected),
        ),
        patch("backend.agents.classifier.classify_heuristic") as heuristic_mock,
    ):
        await classify(STEM_SAMPLE)

    heuristic_mock.assert_not_called()


@pytest.mark.asyncio
async def test_red_g0_mock_mode_must_not_call_classify_with_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """G.0 / G.4: LLM_MODE=mock 零 live 调用。"""
    monkeypatch.setenv("LLM_MODE", "mock")
    get_settings.cache_clear()

    with patch("backend.agents.classifier.classify_with_llm", new=AsyncMock()) as llm_mock:
        await classify(STEM_SAMPLE)

    llm_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_red_g1_llm_rejects_third_paradigm_value(
    live_classify_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """G.0 / G.1: 不允许第三类 paradigm。"""
    _ = live_classify_env
    bad = ParadigmClassification.model_construct(
        paradigm="MIXED",  # type: ignore[arg-type]
        confidence=0.5,
        reason="invalid",
    )
    structured_runnable = MagicMock()
    structured_runnable.ainvoke = AsyncMock(return_value=bad)
    chat = MagicMock()
    chat.with_structured_output.return_value = structured_runnable
    client = LlmClient()
    client._chat = chat
    client._fallback_chat = None

    monkeypatch.setenv("CLASSIFIER_TWO_PHASE_ENABLED", "false")
    get_settings.cache_clear()
    reset_llm_client_cache()

    with pytest.raises(ValueError, match="Invalid paradigm"):
        await classify_with_llm(STEM_SAMPLE, llm_client=client)


@pytest.mark.asyncio
async def test_red_g2_paradigm_classification_json_excludes_classify_warnings() -> None:
    """G.2.8: warnings 与 classification 字段分离。"""
    classification = ParadigmClassification(
        paradigm=Paradigm.HSS,
        confidence=0.85,
        reason="Qualitative study.",
    )
    payload = json.loads(classification.model_dump_json())
    assert "classify_warnings" not in payload
    assert set(payload.keys()) == {"paradigm", "confidence", "reason"}


@pytest.mark.asyncio
async def test_red_g4_heuristic_fallback_false_pipeline_may_fail(
    live_classify_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """G.2.5 / G.4: CLASSIFIER_HEURISTIC_FALLBACK=false → LLM 失败可 failed。"""
    _ = live_classify_env
    monkeypatch.setenv("CLASSIFIER_HEURISTIC_FALLBACK", "false")
    get_settings.cache_clear()
    reset_llm_client_cache()

    with patch(
        "backend.agents.classifier.classify_with_llm",
        new=AsyncMock(side_effect=RuntimeError("structured output failed")),
    ):
        with pytest.raises(ServiceError) as err:
            await classify(STEM_SAMPLE)

    assert err.value.code == "PIPELINE_FAILED"


def test_red_g6_openapi_fixtures_contain_classifier_heuristic_fallback_code() -> None:
    """G.6: fixtures 使用机器码而非用户文案。"""
    for name in ("paper-status-classify-fallback.json", "paper-detail-classify-fallback.json"):
        payload = json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))
        warnings = payload["data"]["classify_warnings"]
        assert warnings == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]
        assert CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE not in json.dumps(payload, ensure_ascii=False)


def test_red_g6_openapi_status_and_detail_both_document_classify_warnings() -> None:
    spec = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))

    def _props(schema_name: str) -> dict:
        schema = spec["components"]["schemas"][schema_name]
        if "properties" in schema:
            return schema["properties"]
        merged: dict = {}
        for item in schema.get("allOf", ()):
            if "properties" in item:
                merged.update(item["properties"])
        return merged

    for schema_name in ("PaperStatusData", "PaperDetail"):
        assert "classify_warnings" in _props(schema_name)


@pytest.mark.parametrize(
    "bad_fixture",
    [
        {"data": {"classify_warnings": CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE}},
        {"data": {"classify_warnings": "classifier_heuristic_fallback"}},
        {"data": {}},
    ],
)
def test_red_g6_fixture_shape_rejects_user_message_as_code(bad_fixture: dict) -> None:
    """G.6 边界：用户文案不得作为 classify_warnings 元素。"""
    warnings = bad_fixture.get("data", {}).get("classify_warnings")
    if isinstance(warnings, list):
        assert CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE not in warnings
    elif warnings is None:
        assert "classify_warnings" not in bad_fixture["data"]


def test_red_g0_no_standalone_classification_route_in_openapi() -> None:
    """G.6 / G.0: 无独立 GET /classification。"""
    spec = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    paths = spec.get("paths", {})
    for path in paths:
        assert "/classification" not in path
