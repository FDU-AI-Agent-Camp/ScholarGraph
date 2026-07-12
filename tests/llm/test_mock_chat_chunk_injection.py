"""Unit tests for context-aware chunk citation injection in MockChat."""

from __future__ import annotations

import re

from backend.llm.mock_chat import (
    MOCK_DISCLAIMER,
    _append_chunk_citation_anchors,
    _extract_authoritative_chunk_ids,
    _mock_qa_response,
    _normalize_chunk_id,
    _should_inject_chunk_citations,
)
from backend.rag.models import QuestionScale
from backend.rag.qa_heuristics import compute_chunk_recall
from backend.schemas.paradigm import Paradigm


def _build_stem_detail_prompt(
    *,
    question: str,
    chunk_lines: list[str],
    paradigm: str = "STEM",
) -> str:
    chunks_block = "\n".join(chunk_lines)
    return f"""## 当前论文范式

{paradigm}

## 知识图谱上下文

### 节点
- [n_method] ResNet-Light (类型: Method)

### 关系
- [n_method] --[evaluated_on]--> [n_dataset]

### 相关原文片段
{chunks_block}

## 用户问题

{question}
"""


def test_normalize_chunk_id_maps_legacy_format() -> None:
    assert _normalize_chunk_id("stem-001_chunk_42") == "stem-001:chunk:42"
    assert _normalize_chunk_id("stem-001:chunk:43") == "stem-001:chunk:43"


def test_extract_authoritative_chunk_ids_from_structured_section() -> None:
    prompt = _build_stem_detail_prompt(
        question="What accuracy on ImageNet?",
        chunk_lines=[
            "- [stem-001:chunk:42] ResNet-Light achieves 78.5% top-1 on ImageNet.",
            "- [stem-001:chunk:43] Learning rate was set to 0.001 with Adam.",
        ],
    )
    assert _extract_authoritative_chunk_ids(prompt) == [
        "stem-001:chunk:42",
        "stem-001:chunk:43",
    ]


def test_extract_authoritative_chunk_ids_normalizes_legacy_brackets() -> None:
    prompt = _build_stem_detail_prompt(
        question="What accuracy on ImageNet?",
        chunk_lines=["- [stem-001_chunk_42] ResNet-Light achieves 78.5% top-1 on ImageNet."],
    )
    assert _extract_authoritative_chunk_ids(prompt) == ["stem-001:chunk:42"]


def test_should_inject_chunk_citations_stem_detail_only() -> None:
    assert _should_inject_chunk_citations(QuestionScale.DETAIL, Paradigm.STEM) is True
    assert _should_inject_chunk_citations(QuestionScale.SUMMARY, Paradigm.STEM) is False
    assert _should_inject_chunk_citations(QuestionScale.VERIFICATION, Paradigm.STEM) is False
    assert _should_inject_chunk_citations(QuestionScale.DETAIL, Paradigm.HSS) is False


def test_append_chunk_citation_anchors_appends_at_end() -> None:
    body = "答案正文。"
    anchored = _append_chunk_citation_anchors(body, ["stem-001:chunk:42", "stem-001:chunk:43"])
    assert anchored.endswith(" [CITE:chunk:stem-001:chunk:42] [CITE:chunk:stem-001:chunk:43]")
    assert anchored.startswith("答案正文。")


def test_mock_qa_response_injects_chunk_cites_before_disclaimer() -> None:
    prompt = _build_stem_detail_prompt(
        question=(
            "What is the top-1 accuracy of the proposed ResNet-Light model "
            "on the ImageNet dataset, and what was the learning rate?"
        ),
        chunk_lines=[
            "- [stem-001:chunk:42] ResNet-Light achieves 78.5% top-1 on ImageNet.",
            "- [stem-001:chunk:43] Learning rate was set to 0.001 with Adam.",
        ],
    )
    response = _mock_qa_response(prompt)
    disclaimer_index = response.index(MOCK_DISCLAIMER)
    chunk_cite_index = response.index("[CITE:chunk:stem-001:chunk:42]")
    assert chunk_cite_index < disclaimer_index
    assert "并引用[CITE:chunk:" not in response


def test_mock_qa_response_hss_detail_skips_chunk_cites() -> None:
    prompt = _build_stem_detail_prompt(
        question="核心论点如何支撑？",
        chunk_lines=["- [hss-001:chunk:1] 制度变迁材料。"],
        paradigm="HSS",
    )
    response = _mock_qa_response(prompt)
    assert "[CITE:chunk:" not in response


def test_mock_qa_response_stem_summary_skips_chunk_cites() -> None:
    prompt = _build_stem_detail_prompt(
        question="这篇论文做了什么？",
        chunk_lines=["- [stem-001:chunk:42] ResNet-Light summary chunk."],
    )
    response = _mock_qa_response(prompt)
    assert "[CITE:chunk:" not in response


def test_mock_chunk_citations_drive_chunk_recall_gate() -> None:
    prompt = _build_stem_detail_prompt(
        question="What accuracy and learning rate?",
        chunk_lines=[
            "- [stem-001:chunk:42] ResNet-Light achieves 78.5% top-1 on ImageNet.",
            "- [stem-001:chunk:43] Learning rate was set to 0.001.",
        ],
    )
    response = _mock_qa_response(prompt)
    citations = [
        {"type": "chunk", "chunk_id": match.group(1)} for match in re.finditer(r"\[CITE:chunk:([^\]]+)\]", response)
    ]
    gold = {"paragraphs": ["stem-001:chunk:42", "stem-001:chunk:43"]}
    recall = compute_chunk_recall(citations, gold)
    assert recall == 1.0
