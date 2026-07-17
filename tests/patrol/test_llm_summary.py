# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for patrol LLM summary helper."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.patrol.llm_summary import generate_patrol_summary
from backend.schemas.patrol import PatrolMode
from backend.schemas.patrol_llm import PatrolSummaryOutput


async def test_generate_patrol_summary_uses_structured_output() -> None:
    mock_client = MagicMock()
    mock_structured = AsyncMock()
    mock_structured.ainvoke.return_value = PatrolSummaryOutput(
        summary="结构化摘要：两篇论文在理论视角上存在潜在冲突，需要进一步对照。",
    )
    mock_client.chat.with_structured_output.return_value = mock_structured

    result = await generate_patrol_summary(
        PatrolMode.LENS_CLASH,
        "paper_id=a, AnalyticalLens=消费社会",
        llm_client=mock_client,
    )
    assert result is not None
    assert "结构化摘要" in result
    mock_client.chat.with_structured_output.assert_called_once_with(PatrolSummaryOutput)


async def test_generate_patrol_summary_returns_none_when_no_api_key() -> None:
    with patch("backend.patrol.llm_summary.get_llm_client", side_effect=ValueError("no key")):
        result = await generate_patrol_summary(PatrolMode.LENS_CLASH, "context")
    assert result is None


async def test_generate_patrol_summary_returns_none_on_llm_failure() -> None:
    mock_client = MagicMock()
    mock_structured = AsyncMock()
    mock_structured.ainvoke.side_effect = RuntimeError("upstream error")
    mock_client.chat.with_structured_output.return_value = mock_structured

    result = await generate_patrol_summary(
        PatrolMode.CONTRADICTION,
        "Thesis: A vs B",
        llm_client=mock_client,
    )
    assert result is None


async def test_generate_patrol_summary_rejects_empty_context() -> None:
    result = await generate_patrol_summary(PatrolMode.LENS_CLASH, "   ")
    assert result is None


def test_patrol_summary_output_schema_constraints() -> None:
    with pytest.raises(ValueError):
        PatrolSummaryOutput(summary="too short")


async def test_generate_patrol_summary_contradiction_uses_contradiction_prompt() -> None:
    mock_client = MagicMock()
    mock_structured = AsyncMock()
    mock_structured.ainvoke.return_value = PatrolSummaryOutput(
        summary="Contradiction 结构化摘要：两篇论文在核心论点层面存在可辨识的论证张力。",
    )
    mock_client.chat.with_structured_output.return_value = mock_structured

    await generate_patrol_summary(
        PatrolMode.CONTRADICTION,
        "paper_id=hss-001\nThesis: A",
        llm_client=mock_client,
    )
    messages = mock_structured.ainvoke.call_args.args[0]
    assert "Contradiction" in messages[0].content
    assert "Thesis" in messages[0].content


async def test_generate_patrol_summary_coerces_non_model_payload() -> None:
    mock_client = MagicMock()
    mock_structured = AsyncMock()
    mock_structured.ainvoke.return_value = {
        "summary": "字典载荷同样可解析为结构化摘要，满足最小长度约束要求。",
    }
    mock_client.chat.with_structured_output.return_value = mock_structured

    result = await generate_patrol_summary(
        PatrolMode.LENS_CLASH,
        "context",
        llm_client=mock_client,
    )
    assert result is not None
    assert "字典载荷" in result


def test_patrol_summary_output_accepts_valid_summary() -> None:
    payload = PatrolSummaryOutput(
        summary="合法摘要：两篇论文在分析视角与核心论点层面均存在可对读的张力，建议进一步核验。",
    )
    assert len(payload.summary) >= 20
