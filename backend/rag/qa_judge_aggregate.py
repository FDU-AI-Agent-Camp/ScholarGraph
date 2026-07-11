"""Bottom-up aggregation: sentence_judgments (Step 1) → macro Judge metrics (Step 2)."""

from __future__ import annotations

import re

from backend.rag.models import SentenceJudgment, SentenceLabel, TrackBJudgeSchema

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？.!?])")


def split_answer_sentences(answer_text: str) -> list[str]:
    """Split model answer into sentence-like units for mock / fallback labeling."""
    text = answer_text.strip()
    if not text:
        return []

    parts = [segment.strip() for segment in _SENTENCE_SPLIT_RE.split(text) if segment.strip()]
    return parts or [text]


def aggregate_sentence_judgments(judgments: list[SentenceJudgment]) -> TrackBJudgeSchema:
    """Derive macro Judge metrics deterministically from micro sentence labels."""
    if not judgments:
        return TrackBJudgeSchema(
            sentence_judgments=[
                SentenceJudgment(sentence="(empty answer)", label=SentenceLabel.SUPPORTED),
            ],
            factual_consistency=1.0,
            hallucination_detected=False,
            reasoning="Bottom-up: 无可切分句子，默认无幻觉。",
        )

    supported = sum(1 for item in judgments if item.label == SentenceLabel.SUPPORTED)
    hallucinated = sum(1 for item in judgments if item.label == SentenceLabel.HALLUCINATED)
    redundant = sum(1 for item in judgments if item.label == SentenceLabel.REDUNDANT)
    total = len(judgments)

    hallucination_detected = hallucinated > 0
    entailment_denominator = supported + hallucinated
    if entailment_denominator == 0:
        factual_consistency = 1.0
    else:
        factual_consistency = supported / entailment_denominator

    reasoning = (
        f"Bottom-up 汇总：共 {total} 句 — "
        f"{supported} supported, {hallucinated} hallucinated, {redundant} redundant；"
        f"factual_consistency={factual_consistency:.2f}, "
        f"hallucination_detected={hallucination_detected}。"
    )

    return TrackBJudgeSchema(
        sentence_judgments=judgments,
        factual_consistency=round(factual_consistency, 4),
        hallucination_detected=hallucination_detected,
        reasoning=reasoning,
    )
