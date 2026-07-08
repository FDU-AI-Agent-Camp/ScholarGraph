"""Tests for V2 RAG hard-rule question scale routing."""

from backend.rag.models import QuestionScale
from backend.rag.qa_router import detect_question_scale


def test_summary_questions_route_to_skeleton_scale() -> None:
    assert detect_question_scale("这篇论文做了什么？") == QuestionScale.SKELETON
    assert detect_question_scale("Give me a short summary of the paper") == QuestionScale.SKELETON


def test_detail_questions_route_to_detail_scale() -> None:
    assert detect_question_scale("论文使用了什么数据集和实验指标？") == QuestionScale.DETAIL
    assert detect_question_scale("What method module reports the metric number?") == QuestionScale.DETAIL


def test_cross_paper_questions_route_to_cross_scale_first() -> None:
    assert detect_question_scale("对比两篇论文的方法差异") == QuestionScale.CROSS_PAPER
    assert detect_question_scale("Compare the experiment differences between two papers") == QuestionScale.CROSS_PAPER


def test_blank_and_unknown_questions_default_to_skeleton() -> None:
    assert detect_question_scale("  ") == QuestionScale.SKELETON
    assert detect_question_scale("请帮我看看") == QuestionScale.SKELETON
