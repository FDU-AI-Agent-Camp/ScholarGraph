"""Hard-rule question-scale router for hybrid RAG (V2 §4.1 / P2-1).

Uses regex + academic keyword tables only — no LLM routing. Returns
``QuestionScale.CROSS_PAPER`` for multi-paper comparison; HTTP routes must
fuse with 400 and redirect users to Patrol.
"""

from __future__ import annotations

import re
from typing import Any

from backend.rag.models import QuestionScale, coerce_question_scale
from backend.schemas.paradigm import Paradigm

CROSS_PAPER_PATROL_GUIDE = "当前问答接口仅支持单篇论文深度解析。若要对比多篇论文，请前往 /patrol 跨论文巡航模块。"

_CROSS_PAPER_KEYWORDS: tuple[str, ...] = (
    "compare to",
    "compare with",
    "compared to",
    "compared with",
    "versus",
    " vs ",
    " vs.",
    "另一篇",
    "其他论文",
    "两篇论文",
    "两篇",
    "多篇文章",
    "跨论文",
    "另一篇文章",
    "上一篇",
    "上一篇论文",
)

_CROSS_PAPER_CN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"对比.*(另一|其他|两篇)"),
    re.compile(r"(矛盾|差异).*(两篇|论文)"),
    re.compile(r"与.*上一篇"),
    re.compile(r"相比.*(上一|另一|其他)"),
)

_PAPER_ID_RE = re.compile(r"\b([a-z][a-z0-9]*-\d{3,})\b", re.IGNORECASE)

# P2-1 numeric feature extractor — upgrades point queries to DETAIL scale.
_NUMERIC_DETAIL_RE = re.compile(r"\b\d+(?:\.\d+)?%?\b")

_VERIFICATION_PHRASES: tuple[str, ...] = (
    "哪些材料",
    "哪些节点",
    "如何论证",
    "如何验证",
    "什么证据",
    "哪些证据",
    "发挥了什么作用",
    "经何种理论视角被论证",
    "通过哪些材料",
    "证据链",
    "实验指标",
    "数据集指标",
)

_DETAIL_KEYWORDS: tuple[str, ...] = (
    "dataset",
    "accuracy",
    "f1-score",
    " f1 ",
    "table",
    "figure",
    "parameter",
    "baseline",
    "metric",
    "hyperparameter",
    "p-value",
    "p value",
    "section ",
    "mnist",
    "imagenet",
    "resnet",
    "数值",
    "数据集",
    "准确率",
    "参数",
    "实验结果",
    "表格",
    "图表",
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
    "逻辑关系",
    "什么关系",
    "提到了哪些",
    "第几页",
    "多少",
    "experiment",
    "page",
    "method",
    "detail",
)

_SUMMARY_KEYWORDS: tuple[str, ...] = (
    "summarize",
    "summary of the main",
    "main contributions",
    "methodology of this work",
    "summarize the methodology",
    "做了什么",
    "研究什么",
    "核心问题",
    "总览",
    "概述",
    "摘要",
    "主要贡献",
    "主要结论",
    "论证框架",
    "学科范式",
    "核心论点是什么",
    "这篇论文",
    "宏观",
    "整体结论",
    "整体",
    "核心论点",
    "this paper",
    "summary",
    "overview",
)

_ENGLISH_WORD_KEYWORDS: frozenset[str] = frozenset(
    {
        "dataset",
        "accuracy",
        "f1-score",
        " f1 ",
        "table",
        "figure",
        "parameter",
        "baseline",
        "metric",
        "hyperparameter",
        "p-value",
        "p value",
        "section ",
        "mnist",
        "imagenet",
        "resnet",
        "experiment",
        "page",
        "method",
        "detail",
        "summarize",
        "summary of the main",
        "main contributions",
        "methodology of this work",
        "summarize the methodology",
        "this paper",
        "summary",
        "overview",
    }
)


def contains_numeric_query(text: str) -> bool:
    """Return True when the question embeds a numeric literal (e.g. ``95.5%``)."""
    return _NUMERIC_DETAIL_RE.search(text) is not None


def detect_cross_paper_intent(
    question: str,
    current_paper_context: dict[str, Any] | None = None,
) -> bool:
    """Detect cross-paper comparison intent before scale routing."""
    normalized = f" {question.strip().lower()} "
    if any(keyword in normalized for keyword in _CROSS_PAPER_KEYWORDS):
        return True
    for pattern in _CROSS_PAPER_CN_PATTERNS:
        if pattern.search(question):
            return True
    return _references_foreign_paper_id(question, current_paper_context)


def detect_question_scale(
    question: str,
    *,
    paradigm: Paradigm | None = None,
    current_paper_context: dict[str, Any] | None = None,
) -> QuestionScale:
    """Classify a user question into summary / detail / verification / cross_paper."""
    text = question.strip()
    if detect_cross_paper_intent(text, current_paper_context):
        return QuestionScale.CROSS_PAPER

    if not text:
        return QuestionScale.SUMMARY

    if _matches_verification(text, paradigm=paradigm):
        return QuestionScale.VERIFICATION
    if _matches_detail(text, paradigm=paradigm):
        return QuestionScale.DETAIL
    if _matches_summary(text):
        return QuestionScale.SUMMARY
    return QuestionScale.SUMMARY


def preferred_node_types(scale: QuestionScale, *, paradigm: Paradigm) -> tuple[str, ...]:
    """Node types to prefer when picking citations for *scale*."""
    if scale == QuestionScale.CROSS_PAPER:
        return ()
    if scale == QuestionScale.SUMMARY:
        return ("Thesis", "ResearchQuestion")
    if scale == QuestionScale.DETAIL:
        if paradigm == Paradigm.STEM:
            return ("Method", "SubArgument", "Claim")
        return ("SubArgument", "Method", "Thesis")
    if paradigm == Paradigm.STEM:
        return ("Evidence", "Claim", "Dataset", "Experiment")
    return ("AnalyticalLens", "ObjectOrData", "Evidence", "Thesis")


def _references_foreign_paper_id(question: str, context: dict[str, Any] | None) -> bool:
    if context is None:
        return False
    current = str(context.get("paper_id", "")).strip().lower()
    if not current:
        return False
    for match in _PAPER_ID_RE.finditer(question):
        if match.group(1).lower() != current:
            return True
    return False


def _matches_verification(text: str, *, paradigm: Paradigm | None) -> bool:
    if any(phrase in text for phrase in _VERIFICATION_PHRASES):
        return True
    if paradigm == Paradigm.STEM and any(token in text for token in ("实验", "指标", "验证")):
        if any(token in text for token in ("哪些", "如何", "是否", "证据")):
            return True
    if paradigm == Paradigm.HSS:
        if "材料" in text and ("哪些" in text or "如何" in text):
            return True
        if "史料" in text and ("哪些" in text or "如何" in text):
            return True
    return False


def _matches_detail(text: str, *, paradigm: Paradigm | None) -> bool:
    lowered = text.lower()
    if any(_keyword_matches(lowered, keyword) for keyword in _DETAIL_KEYWORDS):
        return True
    if contains_numeric_query(text):
        return True
    if paradigm == Paradigm.STEM and any(token in text for token in ("方法", "模块", "架构")):
        return True
    if paradigm == Paradigm.HSS and any(token in text for token in ("分论点", "支撑", "理论视角")):
        if "哪些材料" not in text and "如何论证" not in text:
            return True
    return False


def _matches_summary(text: str) -> bool:
    lowered = text.lower()
    return any(_keyword_matches(lowered, keyword) for keyword in _SUMMARY_KEYWORDS)


def _keyword_matches(text: str, keyword: str) -> bool:
    normalized = keyword.strip().lower()
    if not normalized:
        return False
    if normalized in _ENGLISH_WORD_KEYWORDS:
        return re.search(rf"\b{re.escape(normalized)}\b", text) is not None
    return normalized in text


__all__ = [
    "CROSS_PAPER_PATROL_GUIDE",
    "QuestionScale",
    "coerce_question_scale",
    "contains_numeric_query",
    "detect_cross_paper_intent",
    "detect_question_scale",
    "preferred_node_types",
]
