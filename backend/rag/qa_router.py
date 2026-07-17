# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Hard-rule question-scale router for hybrid RAG (V2 §4.1 / P2-1).

Uses regex + academic keyword tables only — no LLM routing. Returns
``QuestionScale.CROSS_PAPER`` for multi-paper comparison; HTTP routes must
fuse with 400 and redirect users to Patrol.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from backend.rag.models import QuestionScale, coerce_question_scale
from backend.schemas.paradigm import Paradigm

CROSS_PAPER_PATROL_GUIDE = "当前问答接口仅支持单篇论文深度解析。若要对比多篇论文，请前往 /patrol 跨论文巡航模块。"

_PAPER_ID_RE = re.compile(r"\b([a-z][a-z0-9]*-\d{3,})\b", re.IGNORECASE)

# P2-1 numeric feature extractor — upgrades point queries to DETAIL scale.
_NUMERIC_DETAIL_RE = re.compile(r"\b\d+(?:\.\d+)?%?\b")


@dataclass(frozen=True, slots=True)
class ScaleRoutingRules:
    """Structured hard-rule tables for question-scale routing (no LLM)."""

    cross_paper_keywords: tuple[str, ...]
    cross_paper_cn_patterns: tuple[re.Pattern[str], ...]
    verification_phrases: tuple[str, ...]
    macro_preemption_keywords: tuple[str, ...]
    macro_preemption_patterns: tuple[re.Pattern[str], ...]
    detail_keywords: tuple[str, ...]
    detail_relation_patterns: tuple[re.Pattern[str], ...]
    detail_relation_exclusions: tuple[re.Pattern[str], ...]
    summary_keywords: tuple[str, ...]
    english_word_keywords: frozenset[str]


DEFAULT_SCALE_ROUTING_RULES = ScaleRoutingRules(
    cross_paper_keywords=(
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
    ),
    cross_paper_cn_patterns=(
        re.compile(r"对比.*(另一|其他|两篇)"),
        re.compile(r"(矛盾|差异).*(两篇|论文)"),
        re.compile(r"与.*上一篇"),
        re.compile(r"相比.*(上一|另一|其他)"),
    ),
    verification_phrases=(
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
    ),
    macro_preemption_keywords=(
        "整篇",
        "演进脉络",
        "总体而言",
        "总体上看",
        "全文脉络",
        "宏观脉络",
        "全文视角",
    ),
    macro_preemption_patterns=(
        re.compile(r"总体.*(观点|结论|脉络|框架|贡献)"),
        re.compile(r"整篇.*(论文|文章|研究)"),
        re.compile(r"对比\s*(两篇|两构型|两种方法|两个论文)"),
        re.compile(r"(两篇|两构型).{0,16}对比"),
    ),
    detail_keywords=(
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
        "与基线",
        "区别",
        "采用了",
        "分析",
        "提到了哪些",
        "第几页",
        "多少",
        "experiment",
        "page",
        "method",
        "detail",
    ),
    detail_relation_patterns=(
        re.compile(
            r"(实体|节点|指标|数据集|分论点|核心论点|理论视角|论证|方法|模块|基线|"
            r"claim|metric|dataset|method|node|lens_of).{0,24}(关系|逻辑关系)",
            re.IGNORECASE,
        ),
        re.compile(
            r"(关系|逻辑关系).{0,24}(实体|节点|指标|数据集|分论点|核心论点|理论视角|节点)",
            re.IGNORECASE,
        ),
        re.compile(r"与.{1,36}(关系|逻辑关系)"),
        re.compile(r"之间.{0,12}(是什么|有).{0,8}(逻辑)?关系"),
        re.compile(r"存在.{0,8}什么关系"),
        re.compile(r"论证关系"),
        re.compile(r"(是什么关系|有何关联|什么关系)\s*[？?]"),
        re.compile(r"LENS_OF\s*关系", re.IGNORECASE),
    ),
    detail_relation_exclusions=(
        re.compile(r"(这两篇|两篇论文|两构型|两种构型|方法论|整体结论|论文结论|全文).{0,30}(关系|逻辑关系)"),
        re.compile(r"(关系|逻辑关系).{0,16}(这两篇|两篇论文|两构型|方法论)"),
    ),
    summary_keywords=(
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
    ),
    english_word_keywords=frozenset(
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
    ),
)


def contains_numeric_query(text: str) -> bool:
    """Return True when the question embeds a numeric literal (e.g. ``95.5%``)."""
    return _NUMERIC_DETAIL_RE.search(text) is not None


def detect_cross_paper_intent(
    question: str,
    current_paper_context: dict[str, Any] | None = None,
    *,
    rules: ScaleRoutingRules = DEFAULT_SCALE_ROUTING_RULES,
) -> bool:
    """Detect cross-paper comparison intent before scale routing."""
    normalized = f" {question.strip().lower()} "
    if any(keyword in normalized for keyword in rules.cross_paper_keywords):
        return True
    for pattern in rules.cross_paper_cn_patterns:
        if pattern.search(question):
            return True
    return _references_foreign_paper_id(question, current_paper_context)


def detect_question_scale(
    question: str,
    *,
    paradigm: Paradigm | None = None,
    current_paper_context: dict[str, Any] | None = None,
    rules: ScaleRoutingRules = DEFAULT_SCALE_ROUTING_RULES,
) -> QuestionScale:
    """Classify a user question into summary / detail / verification / cross_paper."""
    text = question.strip()
    if detect_cross_paper_intent(text, current_paper_context, rules=rules):
        return QuestionScale.CROSS_PAPER

    if not text:
        return QuestionScale.SUMMARY

    if _matches_verification(text, paradigm=paradigm, rules=rules):
        return QuestionScale.VERIFICATION
    if _matches_macro_preemption(text, rules=rules):
        return QuestionScale.SUMMARY
    if _matches_detail(text, paradigm=paradigm, rules=rules):
        return QuestionScale.DETAIL
    if _matches_summary(text, rules=rules):
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


def _matches_verification(text: str, *, paradigm: Paradigm | None, rules: ScaleRoutingRules) -> bool:
    if any(phrase in text for phrase in rules.verification_phrases):
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


def _matches_macro_preemption(text: str, *, rules: ScaleRoutingRules) -> bool:
    """Macro intent wins over DETAIL keyword hits (e.g. bare 「关系」)."""
    if any(keyword in text for keyword in rules.macro_preemption_keywords):
        return True
    return any(pattern.search(text) for pattern in rules.macro_preemption_patterns)


def _matches_contextual_detail_relation(text: str, *, rules: ScaleRoutingRules) -> bool:
    """Entity-level 「关系」 phrases only; macro paper-level wording is excluded."""
    if any(pattern.search(text) for pattern in rules.detail_relation_exclusions):
        return False
    return any(pattern.search(text) for pattern in rules.detail_relation_patterns)


def _matches_detail(text: str, *, paradigm: Paradigm | None, rules: ScaleRoutingRules) -> bool:
    lowered = text.lower()
    if any(_keyword_matches(lowered, keyword, rules) for keyword in rules.detail_keywords):
        return True
    if _matches_contextual_detail_relation(text, rules=rules):
        return True
    if contains_numeric_query(text):
        return True
    if paradigm == Paradigm.STEM and any(token in text for token in ("方法", "模块", "架构")):
        return True
    if paradigm == Paradigm.HSS and any(token in text for token in ("分论点", "支撑", "理论视角")):
        if "哪些材料" not in text and "如何论证" not in text:
            return True
    return False


def _matches_summary(text: str, *, rules: ScaleRoutingRules) -> bool:
    lowered = text.lower()
    return any(_keyword_matches(lowered, keyword, rules) for keyword in rules.summary_keywords)


def _keyword_matches(text: str, keyword: str, rules: ScaleRoutingRules) -> bool:
    normalized = keyword.strip().lower()
    if not normalized:
        return False
    if normalized in rules.english_word_keywords:
        return re.search(rf"\b{re.escape(normalized)}\b", text) is not None
    return normalized in text


__all__ = [
    "CROSS_PAPER_PATROL_GUIDE",
    "DEFAULT_SCALE_ROUTING_RULES",
    "QuestionScale",
    "ScaleRoutingRules",
    "coerce_question_scale",
    "contains_numeric_query",
    "detect_cross_paper_intent",
    "detect_question_scale",
    "preferred_node_types",
]
