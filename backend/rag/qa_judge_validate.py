"""Safe parsing / repair for adversarial or contradictory Track B Judge payloads."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from backend.rag.models import JudgeMicroOutput, SentenceJudgment, SentenceLabel, TrackBJudgeSchema
from backend.rag.qa_judge_aggregate import aggregate_sentence_judgments

logger = logging.getLogger(__name__)

_VALIDATOR_REPAIR_PREFIX = "Validator repair:"


def compute_micro_hallucination_sentence_rate(judgments: list[SentenceJudgment]) -> float:
    """Share of sentences labeled hallucinated (0.0–1.0)."""
    if not judgments:
        return 0.0
    hallucinated = sum(1 for item in judgments if item.label == SentenceLabel.HALLUCINATED)
    return hallucinated / len(judgments)


def _parse_sentence_judgments(raw_items: list[Any]) -> list[SentenceJudgment]:
    return [SentenceJudgment.model_validate(item) for item in raw_items]


def _fallback_high_risk_judge(reason: str) -> TrackBJudgeSchema:
    return TrackBJudgeSchema(
        sentence_judgments=[
            SentenceJudgment(
                sentence="(unparseable judge output)",
                label=SentenceLabel.HALLUCINATED,
            ),
        ],
        factual_consistency=0.0,
        hallucination_detected=True,
        reasoning=f"Validator fallback: {reason}",
    )


def safe_parse_track_b_judge(payload: dict[str, Any]) -> tuple[TrackBJudgeSchema, bool]:
    """Parse Judge JSON; on macro/micro contradiction, repair from sentence_judgments.

    Returns:
        (TrackBJudgeSchema, was_repaired) — ``was_repaired`` is True when ValidationError
        was caught and macro fields were recomputed or degraded to hallucination risk.
    """
    try:
        return TrackBJudgeSchema.model_validate(payload), False
    except ValidationError as exc:
        logger.warning("track_b_judge_validation_failed: %s", exc)

        raw_judgments = payload.get("sentence_judgments")
        if isinstance(raw_judgments, list) and raw_judgments:
            try:
                judgments = _parse_sentence_judgments(raw_judgments)
                repaired = aggregate_sentence_judgments(judgments)
                repaired.reasoning = (
                    f"{_VALIDATOR_REPAIR_PREFIX} macro/micro contradiction; "
                    f"recomputed from {len(judgments)} sentence_judgments. {repaired.reasoning}"
                )
                return repaired, True
            except ValidationError:
                pass

        return _fallback_high_risk_judge("contradictory or invalid Judge JSON"), True


def resolve_judge_output(raw: JudgeMicroOutput | TrackBJudgeSchema | dict[str, Any]) -> TrackBJudgeSchema:
    """Normalize Step-1 micro or full Judge payloads into a consistent TrackBJudgeSchema."""
    if isinstance(raw, JudgeMicroOutput):
        return aggregate_sentence_judgments(raw.sentence_judgments)
    if isinstance(raw, TrackBJudgeSchema):
        result, _repaired = safe_parse_track_b_judge(raw.model_dump())
        return result
    if isinstance(raw, dict):
        if "hallucination_detected" in raw:
            result, _repaired = safe_parse_track_b_judge(raw)
            return result
        micro = JudgeMicroOutput.model_validate(raw)
        return aggregate_sentence_judgments(micro.sentence_judgments)
    raise TypeError(f"Unsupported judge output type: {type(raw)!r}")
