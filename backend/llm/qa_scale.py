"""Question-scale detection for multi-scale QA (M2 / A-09)."""

from __future__ import annotations

from backend.rag.models import QuestionScale
from backend.schemas.paradigm import Paradigm

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
    "具体",
    "关系",
    "与基线",
    "区别",
    "采用了",
    "分析",
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
    "哪些节点",
    "发挥了什么作用",
)


def detect_question_scale(question: str, *, paradigm: Paradigm | None = None) -> QuestionScale:
    """Classify a user question into summary / detail / verification scale."""
    text = question.strip()
    if not text:
        return QuestionScale.SUMMARY

    scores = {
        QuestionScale.SUMMARY: _score_hints(text, _SUMMARY_HINTS),
        QuestionScale.DETAIL: _score_hints(text, _DETAIL_HINTS),
        QuestionScale.VERIFICATION: _score_hints(text, _VERIFICATION_HINTS),
    }

    if paradigm == Paradigm.STEM:
        if "实验" in text or "数据集" in text or "基线" in text:
            scores[QuestionScale.VERIFICATION] += 1.5
        if "方法" in text or "模块" in text:
            scores[QuestionScale.DETAIL] += 1.0
    elif paradigm == Paradigm.HSS:
        if "材料" in text or "史料" in text:
            scores[QuestionScale.VERIFICATION] += 1.5
        if "分论点" in text or "支撑" in text:
            scores[QuestionScale.DETAIL] += 1.0
        # "理论视角" alone often marks structural detail; require evidence/material cues for verification.
        if "理论视角" in text and ("材料" in text or "论证" in text or "哪些" in text):
            scores[QuestionScale.VERIFICATION] += 1.5

    best_score = max(scores.values())
    if best_score == 0:
        return QuestionScale.SUMMARY
    tied = [scale for scale, score in scores.items() if score == best_score]
    if len(tied) == 1:
        return tied[0]
    # Prefer the most evidence-seeking scale when keyword scores tie.
    for preferred in (QuestionScale.VERIFICATION, QuestionScale.DETAIL, QuestionScale.SUMMARY):
        if preferred in tied:
            return preferred
    return QuestionScale.SUMMARY


def preferred_node_types(scale: QuestionScale, *, paradigm: Paradigm) -> tuple[str, ...]:
    """Node types to prefer when picking citations for *scale*."""
    if scale == QuestionScale.SUMMARY:
        return ("Thesis", "ResearchQuestion")
    if scale == QuestionScale.DETAIL:
        if paradigm == Paradigm.STEM:
            return ("Method", "SubArgument", "Claim")
        return ("SubArgument", "Method", "Thesis")
    if paradigm == Paradigm.STEM:
        return ("Evidence", "Claim", "Dataset", "Experiment")
    return ("AnalyticalLens", "ObjectOrData", "Evidence", "Thesis")


def _score_hints(text: str, hints: tuple[str, ...]) -> float:
    return float(sum(1 for hint in hints if hint in text))
