"""Tests for native Judge structured output and static snapshot mocks."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.rag.models import JudgeMicroOutput, JudgeSchema
from backend.rag.qa_heuristics import run_heuristic_guardrails
from backend.rag.qa_judge import build_dual_track_evaluation, invoke_qa_judge
from backend.rag.qa_judge_structured import invoke_judge_structured_output
from tests.fixtures.qa_judge_snapshot import load_qa_judge_micro_snapshot, load_qa_judge_snapshot


@pytest.mark.asyncio
async def test_invoke_judge_structured_output_uses_with_structured_output() -> None:
    micro = load_qa_judge_micro_snapshot()
    structured_runnable = MagicMock()
    structured_runnable.ainvoke = AsyncMock(return_value=micro)
    chat = MagicMock()
    chat.with_structured_output.return_value = structured_runnable

    client = MagicMock()
    client.chat = chat

    result = await invoke_judge_structured_output(client, messages=[])
    assert result == micro
    chat.with_structured_output.assert_called_once_with(JudgeSchema)
    structured_runnable.ainvoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_invoke_qa_judge_live_path_aggregates_micro_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.config import get_settings
    from backend.llm.client import get_judge_llm_client, reset_llm_client_cache

    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    get_settings.cache_clear()
    reset_llm_client_cache()

    micro = load_qa_judge_micro_snapshot()
    expected = load_qa_judge_snapshot()

    async def _return_micro(_client: object, _messages: object, **_kwargs: object) -> JudgeMicroOutput:
        return micro

    with patch("backend.rag.qa_judge.invoke_judge_structured_output", side_effect=_return_micro):
        result = await invoke_qa_judge(
            get_judge_llm_client(),
            question="STEM accuracy?",
            paradigm="STEM",
            answer_text="F1 达到 15%",
            citations=[],
            gold={"required_patterns": ["15%"], "forbidden_patterns": [], "nodes": [], "edges": []},
        )

    assert result == expected
    assert result.sentence_judgments


def test_snapshot_dual_track_evaluation_is_repeatable() -> None:
    guardrails = run_heuristic_guardrails(
        "F1 达到 15% 在 ImageNet 上验证",
        [{"type": "node", "node_id": "n1"}],
        {
            "nodes": ["n1"],
            "edges": [],
            "required_patterns": ["15%", "ImageNet"],
            "forbidden_patterns": [],
        },
    )
    evaluation = build_dual_track_evaluation(guardrails, load_qa_judge_snapshot())
    assert evaluation["faithfulness"]["hallucination_rate"] == 0.0
    assert evaluation["faithfulness"]["semantic_alignment"] == 1.0
    assert evaluation["judge"]["sentence_judgments"]
    assert evaluation["judge"]["reasoning"].startswith("Bottom-up")
