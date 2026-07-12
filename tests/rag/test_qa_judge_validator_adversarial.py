"""Adversarial Mock tests for TrackBJudgeSchema validator repair and fuse mapping."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from backend.rag.models import SentenceJudgment, SentenceLabel, TrackBJudgeSchema
from backend.rag.qa_heuristics import run_heuristic_guardrails
from backend.rag.qa_judge import build_dual_track_evaluation, invoke_qa_judge
from backend.rag.qa_judge_validate import (
    compute_micro_hallucination_sentence_rate,
    resolve_judge_output,
    safe_parse_track_b_judge,
)
from pydantic import ValidationError


def test_raw_contradictory_payload_triggers_validation_error() -> None:
    adversarial = {
        "sentence_judgments": [{"sentence": "编造事实。", "label": "hallucinated"}],
        "hallucination_detected": False,
        "factual_consistency": 1.0,
        "reasoning": "LLM incorrectly claims no hallucination.",
    }
    with pytest.raises(ValidationError, match="hallucination_detected"):
        TrackBJudgeSchema.model_validate(adversarial)


def test_safe_parse_repairs_macro_micro_contradiction_without_crash() -> None:
    adversarial = {
        "sentence_judgments": [{"sentence": "编造事实。", "label": "hallucinated"}],
        "hallucination_detected": False,
        "factual_consistency": 1.0,
        "reasoning": "LLM incorrectly claims no hallucination.",
    }

    result, was_repaired = safe_parse_track_b_judge(adversarial)

    assert was_repaired is True
    assert result.hallucination_detected is True
    assert result.factual_consistency == 0.0
    assert "Validator repair" in result.reasoning

    guardrails = run_heuristic_guardrails(
        "正常回答。",
        [],
        {"required_patterns": [], "forbidden_patterns": [], "nodes": [], "edges": []},
    )
    evaluation = build_dual_track_evaluation(guardrails, result)
    assert evaluation["faithfulness"]["hallucination_rate"] == 1.0
    assert evaluation["dual_track"]["hallucination_fused"] is True


def test_two_of_five_hallucinated_sentences_maps_to_micro_rate_and_fuse() -> None:
    judgments = [
        SentenceJudgment(sentence=f"句{i}。", label=SentenceLabel.HALLUCINATED if i <= 2 else SentenceLabel.SUPPORTED)
        for i in range(1, 6)
    ]
    assert compute_micro_hallucination_sentence_rate(judgments) == pytest.approx(0.4)

    contradictory_macro = {
        "sentence_judgments": [item.model_dump() for item in judgments],
        "hallucination_detected": False,
        "factual_consistency": 1.0,
        "reasoning": "LLM missed 40% hallucinated sentences.",
    }

    result, was_repaired = safe_parse_track_b_judge(contradictory_macro)

    assert was_repaired is True
    assert result.hallucination_detected is True
    assert result.factual_consistency == pytest.approx(0.6)
    assert len(result.sentence_judgments) == 5

    guardrails = run_heuristic_guardrails(
        "句1。句2。句3。句4。句5。",
        [],
        {"required_patterns": [], "forbidden_patterns": [], "nodes": [], "edges": []},
    )
    evaluation = build_dual_track_evaluation(guardrails, result)
    assert evaluation["faithfulness"]["hallucination_rate"] == 1.0
    assert evaluation["faithfulness"]["semantic_alignment"] == pytest.approx(0.6)
    assert evaluation["dual_track"]["judge_hallucination_detected"] is True


def test_resolve_judge_output_accepts_micro_and_full_dict() -> None:
    micro_payload = {
        "sentence_judgments": [{"sentence": "OK。", "label": "supported"}],
    }
    micro_result = resolve_judge_output(micro_payload)
    assert micro_result.hallucination_detected is False

    full_payload = {
        "sentence_judgments": [{"sentence": "编造。", "label": "hallucinated"}],
        "hallucination_detected": False,
        "factual_consistency": 1.0,
        "reasoning": "bad",
    }
    repaired = resolve_judge_output(full_payload)
    assert repaired.hallucination_detected is True


@pytest.mark.asyncio
async def test_invoke_qa_judge_catches_adversarial_judge_client_response(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.config import get_settings
    from backend.llm.client import get_judge_llm_client, reset_llm_client_cache

    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    get_settings.cache_clear()
    reset_llm_client_cache()

    adversarial_full = {
        "sentence_judgments": [{"sentence": "无依据推断。", "label": "hallucinated"}],
        "hallucination_detected": False,
        "factual_consistency": 0.95,
        "reasoning": "Looks fine to LLM.",
    }

    async def _return_adversarial(_client: object, _messages: object, **_kwargs: object) -> dict[str, Any]:
        return adversarial_full

    with patch("backend.rag.qa_judge.invoke_judge_structured_output", side_effect=_return_adversarial):
        with patch("backend.rag.qa_judge.resolve_judge_output", wraps=resolve_judge_output) as wrapped_resolve:
            result = await invoke_qa_judge(
                get_judge_llm_client(),
                question="q",
                paradigm="HSS",
                answer_text="无依据推断。",
                citations=[],
                gold={"required_patterns": [], "forbidden_patterns": [], "nodes": [], "edges": []},
            )

    wrapped_resolve.assert_called_once()
    assert result.hallucination_detected is True
    assert result.factual_consistency == 0.0

    guardrails = run_heuristic_guardrails(
        "无依据推断。",
        [],
        {"required_patterns": [], "forbidden_patterns": [], "nodes": [], "edges": []},
    )
    assert build_dual_track_evaluation(guardrails, result)["faithfulness"]["hallucination_rate"] == 1.0


@pytest.mark.asyncio
async def test_invoke_qa_judge_mock_intercept_returns_repaired_five_sentence_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.config import get_settings
    from backend.llm.client import get_judge_llm_client, reset_llm_client_cache

    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    get_settings.cache_clear()
    reset_llm_client_cache()

    judgments = [{"sentence": f"句{i}。", "label": "hallucinated" if i <= 2 else "supported"} for i in range(1, 6)]
    adversarial = {
        "sentence_judgments": judgments,
        "hallucination_detected": False,
        "factual_consistency": 1.0,
        "reasoning": "All good says LLM.",
    }

    async def _fake_structured(_client: object, _messages: object, **_kwargs: object) -> dict[str, Any]:
        return adversarial

    async def _run_op(op: Any) -> Any:
        return await op()

    with patch("backend.rag.qa_judge.invoke_judge_structured_output", side_effect=_fake_structured):
        with patch("backend.rag.qa_judge.run_with_judge_retry", side_effect=_run_op):
            result = await invoke_qa_judge(
                get_judge_llm_client(),
                question="q",
                paradigm="STEM",
                answer_text="句1。句2。句3。句4。句5。",
                citations=[],
                gold={"required_patterns": [], "forbidden_patterns": [], "nodes": [], "edges": []},
            )

    assert compute_micro_hallucination_sentence_rate(result.sentence_judgments) == pytest.approx(0.4)
    assert result.hallucination_detected is True
    assert result.factual_consistency == pytest.approx(0.6)
