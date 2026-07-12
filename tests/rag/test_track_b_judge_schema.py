"""Tests for TrackBJudgeSchema Pydantic consistency validator."""

from __future__ import annotations

import pytest
from backend.rag.models import SentenceJudgment, SentenceLabel, TrackBJudgeSchema
from pydantic import ValidationError


def test_track_b_schema_accepts_consistent_macro_and_micro() -> None:
    result = TrackBJudgeSchema(
        sentence_judgments=[
            SentenceJudgment(sentence="正确。", label=SentenceLabel.SUPPORTED),
            SentenceJudgment(sentence="编造。", label=SentenceLabel.HALLUCINATED),
        ],
        hallucination_detected=True,
        factual_consistency=0.5,
        reasoning="One hallucinated sentence detected.",
    )
    assert result.hallucination_detected is True


def test_track_b_schema_rejects_hallucinated_sentence_with_false_macro_flag() -> None:
    with pytest.raises(ValidationError, match="hallucination_detected"):
        TrackBJudgeSchema(
            sentence_judgments=[
                SentenceJudgment(sentence="编造。", label=SentenceLabel.HALLUCINATED),
            ],
            hallucination_detected=False,
            factual_consistency=1.0,
            reasoning="Contradictory macro flag.",
        )


def test_track_b_schema_allows_no_hallucination_when_all_supported() -> None:
    result = TrackBJudgeSchema(
        sentence_judgments=[
            SentenceJudgment(sentence="事实 A。", label=SentenceLabel.SUPPORTED),
            SentenceJudgment(sentence="套话。", label=SentenceLabel.REDUNDANT),
        ],
        hallucination_detected=False,
        factual_consistency=1.0,
        reasoning="All factual sentences supported.",
    )
    assert result.hallucination_detected is False
