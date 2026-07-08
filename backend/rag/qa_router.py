"""Hard-rule question scale routing for V2 hybrid RAG."""

from __future__ import annotations

from backend.rag.models import QuestionScale

SKELETON_HINTS: tuple[str, ...] = (
    "核心论点",
    "做了什么",
    "摘要",
    "概述",
    "总览",
    "整体",
    "主要结论",
    "主要贡献",
    "研究什么",
    "main contribution",
    "summary",
    "overview",
)

DETAIL_HINTS: tuple[str, ...] = (
    "方法",
    "数据集",
    "实验",
    "指标",
    "数值",
    "具体",
    "第几页",
    "多少",
    "如何设计",
    "模块",
    "baseline",
    "dataset",
    "experiment",
    "metric",
    "number",
    "page",
    "method",
    "detail",
)

CROSS_PAPER_HINTS: tuple[str, ...] = (
    "对比",
    "矛盾",
    "两篇",
    "差异",
    "共同点",
    "不同",
    "compare",
    "contrast",
    "conflict",
    "difference",
)


def detect_question_scale(question: str) -> QuestionScale:
    """Classify a question into skeleton, detail, or cross-paper retrieval scale."""

    normalized_question = question.strip().lower()
    if not normalized_question:
        return QuestionScale.SKELETON
    if _contains_any(normalized_question, CROSS_PAPER_HINTS):
        return QuestionScale.CROSS_PAPER
    if _contains_any(normalized_question, DETAIL_HINTS):
        return QuestionScale.DETAIL
    return QuestionScale.SKELETON


def _contains_any(text: str, hints: tuple[str, ...]) -> bool:
    return any(hint in text for hint in hints)
