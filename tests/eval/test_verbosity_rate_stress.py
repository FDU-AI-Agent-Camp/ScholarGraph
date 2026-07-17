# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""High-redundancy stress tests for verbosity_rate (character inflation heuristic).

Proves the metric is no longer hard-coded 0.0 and catches answers that pad
recall with verbose fluff while smuggling the gold fact in the final sentence.
"""

from __future__ import annotations

from typing import Any

import pytest
from backend.rag.models import QAJudgeResult, SentenceJudgment, SentenceLabel
from backend.rag.qa_heuristics import (
    compute_verbosity_rate,
    derive_golden_reference_text,
    run_heuristic_guardrails,
)
from backend.rag.qa_judge import build_dual_track_evaluation

# Align with docs/v2/rag-requirements.md QA_VERBOSITY_CEILING
QA_VERBOSITY_CEILING = 0.15

_GOLD_MINIMAL: dict[str, Any] = {
    "nodes": [],
    "edges": [],
    "required_patterns": [],
    "forbidden_patterns": [],
    "reference_answer": "解是 x = 2",
}

_GOLDEN_REFERENCE = "解是 x = 2"
_GOLDEN_CHAR_LEN = len(_GOLDEN_REFERENCE)

_FLUFF_PARAGRAPH = (
    "从理论框架出发，有必要对研究问题进行更为详尽的阐述与反复论证。"
    "首先，我们应当回顾相关文献中的主要观点，并在此基础上逐步展开分析。"
    "其次，考虑到方法论层面的复杂性，本文采用多层次的叙述结构，"
    "以便读者能够更加全面地理解问题背景、研究动机以及可能的延伸讨论。"
    "再次，为了确保论述的完整性，我们还需要补充若干看似相关但实则重复的背景说明，"
    "包括但不限于历史沿革、概念辨析、术语定义、研究范围边界、潜在限制条件、"
    "以及未来可能的研究方向之展望与反思。"
    "综上所述，在充分铺垫之后，我们可以给出如下结论："
)


def _build_high_redundancy_answer(*, target_body_chars: int = 500) -> str:
    """Build ~500 chars of fluff ending with the gold solution."""
    repeats = max(1, target_body_chars // len(_FLUFF_PARAGRAPH) + 1)
    body = (_FLUFF_PARAGRAPH * repeats)[:target_body_chars]
    return f"{body}最终可得，{_GOLDEN_REFERENCE}"


def test_golden_reference_length_matches_reference_answer() -> None:
    assert len(_GOLDEN_REFERENCE) == 8
    assert derive_golden_reference_text(_GOLD_MINIMAL) == _GOLDEN_REFERENCE


def test_high_redundancy_answer_exceeds_five_hundred_chars() -> None:
    answer = _build_high_redundancy_answer(target_body_chars=500)
    assert len(answer.strip()) >= 500
    assert answer.strip().endswith(_GOLDEN_REFERENCE)


def test_verbosity_rate_approaches_one_for_fluff_padding() -> None:
    answer = _build_high_redundancy_answer(target_body_chars=500)
    rate = compute_verbosity_rate(answer, _GOLD_MINIMAL)

    model_len = len(answer.strip())
    expected = 1.0 - _GOLDEN_CHAR_LEN / model_len

    assert rate == pytest.approx(expected, rel=1e-4)
    assert rate > 0.95
    assert rate > QA_VERBOSITY_CEILING


def test_guardrails_surface_verbosity_rate_not_hardcoded_zero() -> None:
    answer = _build_high_redundancy_answer(target_body_chars=500)
    guardrails = run_heuristic_guardrails(answer, [], _GOLD_MINIMAL, paradigm="STEM")

    assert guardrails.golden_reference_length == _GOLDEN_CHAR_LEN
    assert guardrails.answer_char_length >= 500
    assert guardrails.verbosity_rate > 0.95
    assert guardrails.verbosity_rate != 0.0
    assert guardrails.to_dict()["verbosity_rate"] == round(guardrails.verbosity_rate, 4)


def test_dual_track_report_propagates_verbosity_rate() -> None:
    answer = _build_high_redundancy_answer(target_body_chars=500)
    guardrails = run_heuristic_guardrails(answer, [], _GOLD_MINIMAL, paradigm="STEM")
    judge = QAJudgeResult(
        sentence_judgments=[
            SentenceJudgment(sentence="最终可得，解是 x = 2。", label=SentenceLabel.SUPPORTED),
        ],
        factual_consistency=1.0,
        hallucination_detected=False,
        reasoning="Answer contains the gold solution.",
    )

    evaluation = build_dual_track_evaluation(guardrails, judge)

    assert evaluation["directness"]["verbosity_rate"] == pytest.approx(guardrails.verbosity_rate, rel=1e-4)
    assert evaluation["directness"]["verbosity_rate"] > QA_VERBOSITY_CEILING
    assert evaluation["guardrails"]["verbosity_rate"] == evaluation["directness"]["verbosity_rate"]
    assert evaluation["directness"]["verbosity_rate"] != 0.0


def test_concise_correct_answer_has_zero_verbosity_rate() -> None:
    concise = _GOLDEN_REFERENCE
    rate = compute_verbosity_rate(concise, _GOLD_MINIMAL)
    assert rate == 0.0

    guardrails = run_heuristic_guardrails(concise, [], _GOLD_MINIMAL)
    assert guardrails.verbosity_rate == 0.0

    evaluation = build_dual_track_evaluation(
        guardrails,
        QAJudgeResult(
            sentence_judgments=[
                SentenceJudgment(sentence=concise, label=SentenceLabel.SUPPORTED),
            ],
            factual_consistency=1.0,
            hallucination_detected=False,
            reasoning="Concise gold-aligned answer.",
        ),
    )
    assert evaluation["directness"]["verbosity_rate"] == 0.0
