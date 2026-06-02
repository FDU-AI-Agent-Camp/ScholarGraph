"""Question-scale detection for multi-scale QA (M2 / A-09)."""

from __future__ import annotations

from typing import Literal

from backend.schemas.paradigm import Paradigm

QuestionScale = Literal["summary", "detail", "verification"]

_SUMMARY_HINTS: tuple[str, ...] = (
    "做了什么",
    "研究什么",
    "核心问题",
    "总览",
    "概述",
    "摘要",
    "主要贡献",
    "这篇论文",
)

_DETAIL_HINTS: tuple[str, ...] = (
    "分论点",
    "如何支撑",
    "如何设计",
    "模块",
    "方法",
    "论证链",
    "细节",
    "关系",
    "与基线",
    "区别",
)

_VERIFICATION_HINTS: tuple[str, ...] = (
    "哪些材料",
    "如何论证",
    "证据",
    "验证",
    "实验",
    "数据集",
    "指标",
    "声称",
    "成立",
    "何种设定",
    "理论视角",
)


def detect_question_scale(question: str, *, paradigm: Paradigm | None = None) -> QuestionScale:
    """Classify a user question into summary / detail / verification scale."""
    text = question.strip()
    if not text:
        return "summary"

    scores = {
        "summary": _score_hints(text, _SUMMARY_HINTS),
        "detail": _score_hints(text, _DETAIL_HINTS),
        "verification": _score_hints(text, _VERIFICATION_HINTS),
    }

    if paradigm == Paradigm.STEM:
        if "实验" in text or "数据集" in text or "基线" in text:
            scores["verification"] += 1.5
        if "方法" in text or "模块" in text:
            scores["detail"] += 1.0
    elif paradigm == Paradigm.HSS:
        if "材料" in text or "理论视角" in text or "史料" in text:
            scores["verification"] += 1.5
        if "分论点" in text or "支撑" in text:
            scores["detail"] += 1.0

    best_scale = max(scores, key=scores.get)
    if scores[best_scale] == 0:
        return "summary"
    return best_scale  # type: ignore[return-value]


def preferred_node_types(scale: QuestionScale, *, paradigm: Paradigm) -> tuple[str, ...]:
    """Node types to prefer when picking citations for *scale*."""
    if scale == "summary":
        return ("Thesis", "ResearchQuestion")
    if scale == "detail":
        if paradigm == Paradigm.STEM:
            return ("Method", "SubArgument", "Claim")
        return ("SubArgument", "Method", "Thesis")
    if paradigm == Paradigm.STEM:
        return ("Evidence", "Claim", "Dataset", "Experiment")
    return ("AnalyticalLens", "ObjectOrData", "Evidence", "Thesis")


def _score_hints(text: str, hints: tuple[str, ...]) -> float:
    return float(sum(1 for hint in hints if hint in text))
