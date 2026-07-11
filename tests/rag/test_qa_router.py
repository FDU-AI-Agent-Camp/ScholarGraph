"""Question-scale router alignment with golden set (B2 / V2 §4.1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.rag.models import QuestionScale, coerce_question_scale
from backend.rag.qa_router import detect_question_scale
from backend.schemas.paradigm import Paradigm

_GOLDEN_SET_PATH = Path(__file__).resolve().parents[2] / "data" / "qa_golden_set.json"


@pytest.fixture
def golden_items() -> list[dict]:
    data = json.loads(_GOLDEN_SET_PATH.read_text(encoding="utf-8"))
    return data["items"]


def test_question_scale_values_match_golden_vocabulary() -> None:
    golden_values = {member.value for member in QuestionScale}
    assert golden_values == {"summary", "detail", "verification"}


def test_golden_scales_are_valid_question_scale(golden_items: list[dict]) -> None:
    for idx, item in enumerate(golden_items):
        scale = item["scale"]
        assert QuestionScale(scale) == scale, f"Item {idx}: invalid scale={scale!r}"


def test_legacy_skeleton_alias_coerces_to_summary() -> None:
    assert coerce_question_scale("skeleton") == QuestionScale.SUMMARY


@pytest.mark.parametrize(
    ("question", "paradigm", "expected"),
    [
        ("这篇论文做了什么？", None, QuestionScale.SUMMARY),
        ("分论点如何支撑核心论点？", None, QuestionScale.DETAIL),
        (
            "核心论点通过哪些材料、经何种理论视角被论证？",
            Paradigm.HSS,
            QuestionScale.VERIFICATION,
        ),
        (
            "论文采用了什么理论视角来分析问题？",
            Paradigm.HSS,
            QuestionScale.DETAIL,
        ),
    ],
)
def test_detect_question_scale_keyword_routing(
    question: str,
    paradigm: Paradigm | None,
    expected: QuestionScale,
) -> None:
    assert detect_question_scale(question, paradigm=paradigm) == expected


def test_detect_question_scale_matches_golden_labels(golden_items: list[dict]) -> None:
    """Heuristic router should agree with human ``scale`` on the golden set."""
    mismatches: list[str] = []
    for idx, item in enumerate(golden_items):
        paradigm = Paradigm(item["paradigm"])
        expected = QuestionScale(item["scale"])
        detected = detect_question_scale(item["question"], paradigm=paradigm)
        if detected != expected:
            mismatches.append(
                f"item {idx}: gold={expected.value} detected={detected.value} q={item['question']!r}"
            )
    assert not mismatches, "Golden scale mismatches:\n" + "\n".join(mismatches)
