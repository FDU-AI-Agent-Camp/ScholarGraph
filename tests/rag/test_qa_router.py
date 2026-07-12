"""Question-scale router alignment with golden set (B4 / V2 §4.1).

Layered parametrized matrix tests for ``detect_question_scale()`` — each group
maps to one row of the scale-decision acceptance table.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from backend.rag.models import QuestionScale, coerce_question_scale
from backend.rag.qa_router import (
    CROSS_PAPER_PATROL_GUIDE,
    DEFAULT_SCALE_ROUTING_RULES,
    detect_cross_paper_intent,
    detect_question_scale,
)
from backend.schemas.paradigm import Paradigm

_GOLDEN_SET_PATH = Path(__file__).resolve().parents[2] / "data" / "qa_golden_set.json"

_GOLDEN_SCALE_VALUES = frozenset({"summary", "detail", "verification"})

_PAPER_CTX = {"paper_id": "hss-001"}
_STEM_CTX = {"paper_id": "stem-001"}


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
    """存量零退化：15 题金标 ``scale`` 必须与启发式路由 100% 对齐。"""
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
            mismatches.append(f"item {idx}: gold={expected.value} detected={detected.value} q={item['question']!r}")
    assert not mismatches, "Golden scale mismatches:\n" + "\n".join(mismatches)
    assert len(golden_items) == 15, "golden set size drift — update zero-regression baseline explicitly"


# ---------------------------------------------------------------------------
# 1. 尺度决策矩阵分层单元测试（验收表）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        pytest.param(
            "这篇论文的主要贡献是什么？",
            QuestionScale.SUMMARY,
            id="summary-zh-main-contribution",
        ),
        pytest.param(
            "Summarize the methodology of this work.",
            QuestionScale.SUMMARY,
            id="summary-en-methodology",
        ),
    ],
)
def test_matrix_summary_boundary(question: str, expected: QuestionScale) -> None:
    """宏观泛读 → SUMMARY，不触发向量库检索。"""
    assert detect_question_scale(question, current_paper_context=_PAPER_CTX) == expected


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        pytest.param(
            "What dataset did they use in section 4?",
            QuestionScale.DETAIL,
            id="detail-en-dataset-section",
        ),
        pytest.param(
            "表格 2 里面的准确率是多少？",
            QuestionScale.DETAIL,
            id="detail-zh-table-accuracy",
        ),
    ],
)
def test_matrix_detail_keyword_boundary(question: str, expected: QuestionScale) -> None:
    """学术实体特征词 → DETAIL，必须召回 Vector Chunks。"""
    assert (
        detect_question_scale(
            question,
            paradigm=Paradigm.STEM,
            current_paper_context=_STEM_CTX,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        pytest.param(
            "Why is the accuracy 95.5%?",
            QuestionScale.DETAIL,
            id="detail-numeric-percent",
        ),
        pytest.param(
            "模型在 alpha=0.01 时的表现",
            QuestionScale.DETAIL,
            id="detail-numeric-param-placeholder",
        ),
    ],
)
def test_matrix_detail_numeric_perturbation_boundary(question: str, expected: QuestionScale) -> None:
    """数值/百分比/参数占位符 → DETAIL（正则硬规则）。"""
    assert detect_question_scale(question, current_paper_context=_PAPER_CTX) == expected


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        pytest.param(
            "Can you summarize the performance on ImageNet dataset?",
            QuestionScale.DETAIL,
            id="conflict-summarize-vs-dataset",
        ),
        pytest.param(
            "Please give a summary of the dataset details.",
            QuestionScale.DETAIL,
            id="conflict-summary-of-dataset",
        ),
    ],
)
def test_matrix_detail_overrides_summary_on_weight_conflict(question: str, expected: QuestionScale) -> None:
    """DETAIL 特征词优先于 summarize，防止细节漏召回。"""
    assert (
        detect_question_scale(
            question,
            paradigm=Paradigm.STEM,
            current_paper_context=_STEM_CTX,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        pytest.param(
            "How does this model compare to ResNet50?",
            QuestionScale.CROSS_PAPER,
            id="cross-en-compare-resnet",
        ),
        pytest.param(
            "与上一篇论文相比，它的创新点在哪？",
            QuestionScale.CROSS_PAPER,
            id="cross-zh-previous-paper",
        ),
        pytest.param(
            "Compared to stem-002, how does this method perform?",
            QuestionScale.CROSS_PAPER,
            id="cross-foreign-paper-id",
        ),
    ],
)
def test_matrix_cross_paper_intercept(question: str, expected: QuestionScale) -> None:
    """对比性/外延性提问 → CROSS_PAPER，单篇 QA 必须拦截。"""
    assert detect_question_scale(question, current_paper_context=_PAPER_CTX) == expected


def test_cross_paper_patrol_guide_message() -> None:
    assert "/patrol" in CROSS_PAPER_PATROL_GUIDE
    assert "单篇" in CROSS_PAPER_PATROL_GUIDE


def test_detect_cross_paper_intent_allows_intra_paper_baseline_compare() -> None:
    assert detect_cross_paper_intent("方法与基线对比如何？", _PAPER_CTX) is False


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        pytest.param(
            "总体而言，分论点与核心论点之间是什么关系？",
            QuestionScale.SUMMARY,
            id="macro-preempts-entity-relation",
        ),
        pytest.param(
            "请从演进脉络看这篇论文的核心论点。",
            QuestionScale.SUMMARY,
            id="macro-evolution-arc",
        ),
        pytest.param(
            "整篇论文的论证框架是什么？",
            QuestionScale.SUMMARY,
            id="macro-full-paper-frame",
        ),
    ],
)
def test_matrix_macro_preemption_overrides_detail_relation(question: str, expected: QuestionScale) -> None:
    """宏观限定词抢占 DETAIL，即使出现「关系」也锁定 SUMMARY。"""
    assert detect_question_scale(question, paradigm=Paradigm.HSS, current_paper_context=_PAPER_CTX) == expected


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        pytest.param(
            "理论视角与分论点之间存在什么关系？",
            QuestionScale.DETAIL,
            id="micro-entity-pair-relation",
        ),
        pytest.param(
            "论文中的制度路径依赖论述与核心论点之间是什么逻辑关系？",
            QuestionScale.DETAIL,
            id="micro-logical-relation-between-claims",
        ),
        pytest.param(
            "这两篇论文的方法论有什么关系？",
            QuestionScale.CROSS_PAPER,
            id="macro-methodology-relation-routes-cross",
        ),
        pytest.param(
            "总体而言，这篇论文的结论与引言是什么关系？",
            QuestionScale.SUMMARY,
            id="macro-conclusion-relation-preempted",
        ),
    ],
)
def test_matrix_contextual_detail_relation_regex(question: str, expected: QuestionScale) -> None:
    """实体级「关系」命中 DETAIL；论文级宏观「关系」被排除或抢占。"""
    assert detect_question_scale(question, paradigm=Paradigm.HSS, current_paper_context=_PAPER_CTX) == expected


def test_default_scale_routing_rules_exposes_tunable_negative_relation_exclusions() -> None:
    """Structured rules allow future golden conflicts to be fixed via config only."""
    assert DEFAULT_SCALE_ROUTING_RULES.detail_relation_exclusions
    assert "关系" not in DEFAULT_SCALE_ROUTING_RULES.detail_keywords
    assert "逻辑关系" not in DEFAULT_SCALE_ROUTING_RULES.detail_keywords


# ---------------------------------------------------------------------------
# 影子对抗矩阵（Adversarial Shadow Matrix）— 文本相似、尺度对立
# ---------------------------------------------------------------------------


def test_adversarial_shadow_a_micro_entity_relation_routes_detail() -> None:
    """场景 A：具体技术实体 + 「关系」→ DETAIL（微观向量召回）。"""
    question = "论文中的 ConvNeXt-V2 实体与特征提取网络是什么关系？"
    assert (
        detect_question_scale(
            question,
            paradigm=Paradigm.STEM,
            current_paper_context=_STEM_CTX,
        )
        == QuestionScale.DETAIL
    )


def test_adversarial_shadow_b_macro_methodology_relation_not_detail() -> None:
    """场景 B：跨篇方法论 + 「关系」→ 不得 DETAIL；``两篇论文`` 优先 CROSS_PAPER。"""
    question = "请问这两篇论文在解决时延问题的方法论上，存在什么关系？"
    detected = detect_question_scale(
        question,
        paradigm=Paradigm.STEM,
        current_paper_context=_STEM_CTX,
    )
    assert detected != QuestionScale.DETAIL
    assert detected == QuestionScale.CROSS_PAPER


@pytest.mark.parametrize(
    ("question", "expected", "routing_note"),
    [
        pytest.param(
            "从整篇论文的宏观视角来看，文中提到的 A 驱动与 B 接口之间是什么关系？",
            QuestionScale.SUMMARY,
            "macro-prefix-wins-over-micro-relation-suffix",
            id="boundary-compound-macro-prefix",
        ),
        pytest.param(
            "两者是什么关系？",
            QuestionScale.DETAIL,
            "minimal-context-falls-back-to-detail-vector-recall",
            id="boundary-minimal-relation-fallback",
        ),
    ],
)
def test_adversarial_boundary_multimorpheme_routing(
    question: str,
    expected: QuestionScale,
    routing_note: str,
) -> None:
    """多语素叠加边界：固化短路求值顺序与无语境兜底，防止 Week 6 集成理解漂移。

    - 复合句：``整篇`` 宏观抢占先于尾部实体级「关系」正则 → SUMMARY。
    - 极简句：无上下文时 ``是什么关系`` 兜底 → DETAIL（三类向量稳妥召回）。
    """
    _ = routing_note
    assert (
        detect_question_scale(
            question,
            paradigm=Paradigm.STEM,
            current_paper_context=_STEM_CTX,
        )
        == expected
    )
