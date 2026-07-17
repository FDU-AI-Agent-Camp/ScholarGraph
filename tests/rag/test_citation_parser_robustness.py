# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Fuzzy-match resilience tests for chunk citation parsing in compute_chunk_recall."""

from __future__ import annotations

import pytest
from backend.rag import qa_heuristics as heuristics
from backend.rag.qa_heuristics import (
    compute_chunk_recall,
    extract_chunk_ids_from_text,
    normalize_cited_chunk_id,
    resolve_gold_chunk_ids,
)

_CANONICAL_STEM_42 = "stem-001:chunk:42"
_GOLD_SINGLE_CHUNK = {"paragraphs": [_CANONICAL_STEM_42]}


def _resolved_hits_from_answer(answer_text: str, gold: dict) -> set[str]:
    expected = resolve_gold_chunk_ids(gold)
    hits: set[str] = set()
    for raw_id in extract_chunk_ids_from_text(answer_text):
        resolved = heuristics._resolve_cited_chunk_id(raw_id, expected)
        if resolved:
            hits.add(resolved)
    return hits


@pytest.mark.parametrize(
    ("answer_text", "expected_hits"),
    [
        pytest.param(
            "...依据[CITE : chunk : stem-001_chunk_42]的结论",
            {_CANONICAL_STEM_42},
            id="extra_spaces_around_colons",
        ),
        pytest.param(
            "...参考[CITE:chunk:stem-001_chunk_42] [CITE:chunk:stem-001_chunk_42]",
            {_CANONICAL_STEM_42},
            id="duplicate_markers_deduped",
        ),
        pytest.param(
            "...数据见 [cite:CHUNK:stem-001_chunk_42]",
            {_CANONICAL_STEM_42},
            id="case_insensitive_marker",
        ),
    ],
)
def test_citation_parser_robustness_matrix(answer_text: str, expected_hits: set[str]) -> None:
    assert _resolved_hits_from_answer(answer_text, _GOLD_SINGLE_CHUNK) == expected_hits
    assert compute_chunk_recall([], _GOLD_SINGLE_CHUNK, answer_text=answer_text) == 1.0


def test_citation_parser_rejects_hallucinated_chunk_id_not_in_gold() -> None:
    answer_text = "...根据[CITE:chunk:stem-001_chunk_invalid_999]"
    assert _resolved_hits_from_answer(answer_text, _GOLD_SINGLE_CHUNK) == set()
    assert compute_chunk_recall([], _GOLD_SINGLE_CHUNK, answer_text=answer_text) == 0.0


def test_extract_chunk_ids_from_text_deduplicates_normalized_ids() -> None:
    answer_text = "[CITE:chunk:stem-001_chunk_42] [CITE : chunk : stem-001:chunk:42] [cite:chunk:stem-001_chunk_42]"
    extracted = extract_chunk_ids_from_text(answer_text)
    assert extracted == {_CANONICAL_STEM_42}
    assert normalize_cited_chunk_id("stem-001_chunk_42") == _CANONICAL_STEM_42


def test_duplicate_cites_do_not_inflate_recall_denominator() -> None:
    """Repeated markers must not inflate the cited set or distort recall numerator."""
    gold = {"paragraphs": [_CANONICAL_STEM_42, "stem-001:chunk:43"]}
    answer_text = "[CITE:chunk:stem-001_chunk_42] [CITE:chunk:stem-001_chunk_42] [CITE:chunk:stem-001:chunk:43]"
    assert compute_chunk_recall([], gold, answer_text=answer_text) == 1.0
