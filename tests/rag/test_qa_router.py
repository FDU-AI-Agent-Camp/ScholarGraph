"""Question-scale router alignment with golden set (B4 / V2 §4.1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.rag.models import QuestionScale, coerce_question_scale
from backend.rag.qa_router import (
    CROSS_PAPER_PATROL_GUIDE,
    detect_cross_paper_intent,
    detect_question_scale,
)
from backend.schemas.paradigm import Paradigm

_GOLDEN_SET_PATH = Path(__file__).resolve().parents[2] / "data" / "qa_golden_set.json"

_GOLDEN_SCALE_VALUES = frozenset({"summary", "detail", "verification"})


@pytest.fixture
def golden_items() -> list[dict]:
    data = json.loads(_GOLDEN_SET_PATH.read_text(encoding="utf-8"))
    return data["items"]


def test_question_scale_includes_cross_paper_and_golden_vocabulary() -> None:
    enum_values = {member.value for member in QuestionScale}
    assert QuestionScale.CROSS_PAPER.value in enum_values
    assert _GOLDEN_SCALE_VALUES.issubset(enum_values)


def test_golden_scales_are_valid_question_scale(golden_items: list[dict]) -> None:
    for idx, item in enumerate(golden_items):
        scale = item["scale"]
        assert scale in _GOLDEN_SCALE_VALUES, f"Item {idx}: unexpected scale={scale!r}"
        assert QuestionScale(scale) == scale, f"Item {idx}: invalid scale={scale!r}"


def test_legacy_skeleton_alias_coerces_to_summary() -> None:
    assert coerce_question_scale("skeleton") == QuestionScale.SUMMARY


def test_legacy_cross_alias_coerces_to_cross_paper() -> None:
    assert coerce_question_scale("cross") == QuestionScale.CROSS_PAPER


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
        detected = detect_question_scale(
            item["question"],
            paradigm=paradigm,
            current_paper_context={"paper_id": item["paper_id"]},
        )
        if detected != expected:
            mismatches.append(
                f"item {idx}: gold={expected.value} detected={detected.value} q={item['question']!r}"
            )
    assert not mismatches, "Golden scale mismatches:\n" + "\n".join(mismatches)


# ---------------------------------------------------------------------------
# §3 四组边界参数化压测
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        "Summarize the main contributions of this paper.",
        "请概述这篇论文的主要贡献和论证框架。",
    ],
)
def test_summary_boundary_routing(question: str) -> None:
    assert detect_question_scale(question) == QuestionScale.SUMMARY


@pytest.mark.parametrize(
    "question",
    [
        "What dataset was used in Section 4.1?",
        "表格 2 里面的准确率是多少？",
        "实验在 MNIST 上 accuracy 达到多少？",
        "Table 1 reports 95.5% accuracy — is that on the test split?",
        "Was the reported p-value below 0.05?",
    ],
)
def test_detail_boundary_stem_routing(question: str) -> None:
    assert (
        detect_question_scale(question, paradigm=Paradigm.STEM, current_paper_context={"paper_id": "stem-001"})
        == QuestionScale.DETAIL
    )


@pytest.mark.parametrize(
    "question",
    [
        "How does this model compare to ResNet50?",
        "Compared to stem-002, how does this method perform?",
        "这篇论文与另一篇的差异是什么？",
        "hss-001 和 hss-002 两篇论文矛盾吗？",
    ],
)
def test_cross_paper_boundary_routing(question: str) -> None:
    assert (
        detect_question_scale(question, current_paper_context={"paper_id": "hss-001"})
        == QuestionScale.CROSS_PAPER
    )


def test_cross_paper_patrol_guide_message() -> None:
    assert "/patrol" in CROSS_PAPER_PATROL_GUIDE
    assert "单篇" in CROSS_PAPER_PATROL_GUIDE


def test_detect_cross_paper_intent_allows_intra_paper_baseline_compare() -> None:
    assert detect_cross_paper_intent("方法与基线对比如何？", {"paper_id": "hss-001"}) is False


@pytest.mark.parametrize(
    "question",
    [
        "Please give a summary of the dataset details.",
        "Summarize the dataset used in Section 3.",
    ],
)
def test_mixed_summary_detail_prefers_detail(question: str) -> None:
    """Detail keywords must win over summary cues to preserve chunk recall."""
    assert detect_question_scale(question, paradigm=Paradigm.STEM) == QuestionScale.DETAIL


@pytest.mark.parametrize(
    "question",
    [
        "95.5%",
        "Section 3 mentions 128 hidden units.",
    ],
)
def test_numeric_feature_extractor_routes_to_detail(question: str) -> None:
    assert detect_question_scale(question) == QuestionScale.DETAIL
