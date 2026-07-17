# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Deterministic perception tests for MockChat chunk ID reverse-parsing."""

from __future__ import annotations

import re

from backend.llm.mock_chat import (
    MOCK_DISCLAIMER,
    _extract_authoritative_chunk_ids,
    _mock_qa_response,
    _normalize_chunk_id,
)

_CITE_CHUNK_MARKER_RE = re.compile(r"\[CITE:chunk:([^\]]+)\]")
_STEM_DETAIL_QUESTION = "What is the top-1 accuracy of ResNet-Light on ImageNet, and what learning rate was used?"


def _build_vector_block_prompt(*, chunk_blocks: list[str], paradigm: str = "STEM") -> str:
    chunks_body = "\n".join(chunk_blocks)
    return f"""## 当前论文范式

{paradigm}

## 知识图谱上下文

### 节点
- [n_method] ResNet-Light (类型: Method)

### 关系
- [n_method] --[evaluated_on]--> [n_dataset]

### 相关原文片段
{chunks_body}

## 用户问题

{_STEM_DETAIL_QUESTION}
"""


def _extract_cite_chunk_ids(response: str) -> list[str]:
    return [match.group(1) for match in _CITE_CHUNK_MARKER_RE.finditer(response)]


def _assert_response_cites_chunk(response: str, expected_raw_id: str) -> None:
    expected = _normalize_chunk_id(expected_raw_id)
    cited = {_normalize_chunk_id(chunk_id) for chunk_id in _extract_cite_chunk_ids(response)}
    assert expected in cited, f"expected cite for {expected_raw_id!r}, got markers={list(cited)!r}"


def test_perception_single_vector_block_legacy_id_extraction() -> None:
    """Case 1: parse 【向量块】ID: legacy chunk and inject a stable CITE marker."""
    prompt = _build_vector_block_prompt(
        chunk_blocks=["【向量块 1】ID: stem-001_chunk_42"],
    )
    assert _extract_authoritative_chunk_ids(prompt) == ["stem-001:chunk:42"]

    response = _mock_qa_response(prompt)
    _assert_response_cites_chunk(response, "stem-001_chunk_42")
    assert response.index("[CITE:chunk:stem-001:chunk:42]") < response.index(MOCK_DISCLAIMER)


def test_perception_multi_vector_blocks_deduped_and_appended() -> None:
    """Case 2: two vector blocks inject both IDs in order without marker corruption."""
    prompt = _build_vector_block_prompt(
        chunk_blocks=[
            "【向量块 1】ID: stem-001_chunk_42",
            "【向量块 2】ID: stem-001_chunk_43",
            "【向量块 1】ID: stem-001_chunk_42",
        ],
    )
    assert _extract_authoritative_chunk_ids(prompt) == [
        "stem-001:chunk:42",
        "stem-001:chunk:43",
    ]

    response = _mock_qa_response(prompt)
    markers = _extract_cite_chunk_ids(response)
    assert markers == ["stem-001:chunk:42", "stem-001:chunk:43"]
    _assert_response_cites_chunk(response, "stem-001_chunk_42")
    _assert_response_cites_chunk(response, "stem-001_chunk_43")

    body, tail = response.split(MOCK_DISCLAIMER, maxsplit=1)
    assert tail == ""
    assert body.count("[CITE:chunk:") == 2
    assert "][CITE:chunk:" not in body.replace(" [CITE:chunk:", "")


def test_perception_mock_response_is_repeatable() -> None:
    """Mock injection must be deterministic across repeated generations."""
    prompt = _build_vector_block_prompt(
        chunk_blocks=[
            "【向量块 1】ID: stem-001_chunk_42",
            "【向量块 2】ID: stem-001_chunk_43",
        ],
    )
    baseline = _mock_qa_response(prompt)
    for _ in range(100):
        assert _mock_qa_response(prompt) == baseline
