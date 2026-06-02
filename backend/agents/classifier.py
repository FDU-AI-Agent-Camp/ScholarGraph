"""Paradigm classifier service for BE-2.

Deterministic heuristics when ``LLM_MODE`` is not mock; fixture-backed ``mock_classify``
when ``is_llm_mock`` so CP4 and integration tests need no cloud credentials.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.agents.mock_agents import mock_classify
from backend.config import get_settings
from backend.schemas.paradigm import Paradigm, ParadigmClassification

STEM_KEYWORDS = frozenset(
    {
        "ablation",
        "accuracy",
        "algorithm",
        "baseline",
        "benchmark",
        "dataset",
        "datasets",
        "experiment",
        "experiments",
        "f1",
        "metric",
        "model",
        "performance",
        "quantitative",
        "training",
        "agent",
        "framework",
        "算法",
        "基线",
        "大模型",
        "实验",
        "性能",
        "数据集",
        "框架",
        "模型",
        "消融",
        "准确率",
        "指标",
        "评测",
    }
)
HSS_KEYWORDS = frozenset(
    {
        "archive",
        "discourse",
        "ethnography",
        "historical",
        "history",
        "interview",
        "lens",
        "qualitative",
        "sociology",
        "theoretical",
        "theory",
        "公共领域",
        "制度",
        "劳动者",
        "历史",
        "口岸",
        "叙事",
        "档案",
        "民族志",
        "消费社会",
        "理论",
        "社会",
        "社科",
        "访谈",
        "论证",
        "通商",
        "零工",
        "革命",
        "视角",
        "阐释",
    }
)
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_+\-.]+|[\u4e00-\u9fff]{2,}")


@dataclass(frozen=True)
class KeywordEvidence:
    """Classifier evidence used to build auditable reasons."""

    stem_matches: tuple[str, ...]
    hss_matches: tuple[str, ...]

    @property
    def stem_score(self) -> int:
        return len(self.stem_matches)

    @property
    def hss_score(self) -> int:
        return len(self.hss_matches)


def _normalize_text(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _collect_keyword_evidence(text: str) -> KeywordEvidence:
    normalized = _normalize_text(text)
    tokens = set(TOKEN_PATTERN.findall(normalized))
    stem_matches = sorted(keyword for keyword in STEM_KEYWORDS if keyword.lower() in normalized or keyword in tokens)
    hss_matches = sorted(keyword for keyword in HSS_KEYWORDS if keyword.lower() in normalized or keyword in tokens)
    return KeywordEvidence(tuple(stem_matches), tuple(hss_matches))


def _choose_paradigm(evidence: KeywordEvidence) -> Paradigm:
    if evidence.hss_score > evidence.stem_score:
        return Paradigm.HSS
    if evidence.stem_score > evidence.hss_score:
        return Paradigm.STEM
    return Paradigm.HSS if evidence.hss_score else Paradigm.STEM


def _confidence(evidence: KeywordEvidence) -> float:
    total_matches = evidence.hss_score + evidence.stem_score
    score_gap = abs(evidence.hss_score - evidence.stem_score)
    if total_matches == 0:
        return 0.55
    return min(0.95, 0.62 + 0.07 * score_gap + 0.02 * total_matches)


def _reason(paradigm: Paradigm, evidence: KeywordEvidence) -> str:
    matches = evidence.hss_matches if paradigm == Paradigm.HSS else evidence.stem_matches
    if matches:
        sample = "、".join(matches[:4])
        return f"文本出现 {sample} 等线索，符合 {paradigm.value} 论文的典型结构。"
    return "文本缺少明确学科线索，按默认规则归入 STEM；建议在正式流水线中补充摘要与引言片段。"


async def classify(classifier_input: str) -> ParadigmClassification:
    """Classify a paper snippet as STEM or HSS and return stable JSON."""
    if get_settings().is_llm_mock:
        return mock_classify(classifier_input)

    if not classifier_input or not classifier_input.strip():
        raise ValueError("classifier_input must be a non-empty string.")
    evidence = _collect_keyword_evidence(classifier_input)
    paradigm = _choose_paradigm(evidence)
    return ParadigmClassification(
        paradigm=paradigm,
        confidence=round(_confidence(evidence), 2),
        reason=_reason(paradigm, evidence),
    )
