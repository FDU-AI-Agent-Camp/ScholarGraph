"""Tests for bottom-up sentence_judgments aggregation (Track B Step 2)."""

from __future__ import annotations

from backend.rag.models import SentenceJudgment, SentenceLabel
from backend.rag.qa_judge_aggregate import aggregate_sentence_judgments, split_answer_sentences


def test_split_answer_sentences_handles_chinese_punctuation() -> None:
    parts = split_answer_sentences("第一句。第二句！第三句？")
    assert parts == ["第一句。", "第二句！", "第三句？"]


def test_aggregate_all_supported_yields_full_consistency() -> None:
    result = aggregate_sentence_judgments(
        [
            SentenceJudgment(sentence="事实 A。", label=SentenceLabel.SUPPORTED),
            SentenceJudgment(sentence="事实 B。", label=SentenceLabel.SUPPORTED),
        ],
    )
    assert result.factual_consistency == 1.0
    assert result.hallucination_detected is False
    assert len(result.sentence_judgments) == 2


def test_aggregate_hallucinated_sentence_triggers_detection() -> None:
    result = aggregate_sentence_judgments(
        [
            SentenceJudgment(sentence="正确事实。", label=SentenceLabel.SUPPORTED),
            SentenceJudgment(sentence="编造内容。", label=SentenceLabel.HALLUCINATED),
        ],
    )
    assert result.factual_consistency == 0.5
    assert result.hallucination_detected is True


def test_redundant_sentences_excluded_from_entailment_denominator() -> None:
    result = aggregate_sentence_judgments(
        [
            SentenceJudgment(sentence="有效事实。", label=SentenceLabel.SUPPORTED),
            SentenceJudgment(sentence="重复套话。", label=SentenceLabel.REDUNDANT),
        ],
    )
    assert result.factual_consistency == 1.0
    assert result.hallucination_detected is False
