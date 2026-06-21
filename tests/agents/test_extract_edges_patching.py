"""Tests for chunk-level source_span targeted patching."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from backend.agents.extract_edges import _collect_incomplete_core_edges, _patch_source_spans
from backend.llm.client import LlmClient
from backend.schemas.extract_phase import ExtractedEdge


def _edge(
    edge_id: str = "e1",
    edge_type: str = "SUPPORTS",
    rationale: str | None = "rationale",
    source_span: str | None = None,
) -> ExtractedEdge:
    return ExtractedEdge(
        id=edge_id,
        source="n_evidence",
        target="n_claim",
        label=edge_type,
        type=edge_type,
        rationale=rationale,
        source_span=source_span,
    )


class TestCollectIncompleteCoreEdges:
    def test_collects_core_edges_missing_source_span(self) -> None:
        edges = [
            _edge(edge_id="e1", edge_type="SUPPORTS", source_span=None),
            _edge(edge_id="e2", edge_type="SUPPORTS", source_span="present"),
            _edge(edge_id="e3", edge_type="USES_METHOD", source_span=None),
        ]
        result = _collect_incomplete_core_edges(edges)
        assert len(result) == 1
        assert result[0][0] == 0
        assert result[0][1].id == "e1"

    def test_ignores_non_core_edges(self) -> None:
        edges = [
            _edge(edge_id="e1", edge_type="USES_METHOD", source_span=None),
            _edge(edge_id="e2", edge_type="EVALUATED_ON", source_span=None),
        ]
        result = _collect_incomplete_core_edges(edges)
        assert result == []


@pytest.mark.asyncio
async def test_patch_source_spans_backfills_missing_spans() -> None:
    edges = [
        _edge(edge_id="e1", edge_type="SUPPORTS", source_span=None),
        _edge(edge_id="e2", edge_type="SUPPORTS", source_span=None),
    ]
    text = "The model achieved 95% accuracy. Training took three hours."

    mock_chat = AsyncMock()
    mock_chat.ainvoke.return_value = MagicMock(
        content=json.dumps(
            [
                {"index": 0, "source_span": "The model achieved 95% accuracy."},
                {"index": 1, "source_span": "Training took three hours."},
            ]
        )
    )

    mock_client = MagicMock(spec=LlmClient)
    mock_client.chat = mock_chat

    patched = await _patch_source_spans(edges, text, paper_id="p1", client=mock_client)

    assert patched[0].source_span == "The model achieved 95% accuracy."
    assert patched[1].source_span == "Training took three hours."
    mock_chat.ainvoke.assert_called_once()
    call_kwargs = mock_chat.ainvoke.call_args.kwargs
    assert call_kwargs.get("temperature") == 0.0


@pytest.mark.asyncio
async def test_patch_source_spans_ignores_empty_llm_responses() -> None:
    edges = [_edge(edge_id="e1", edge_type="SUPPORTS", source_span=None)]
    text = "Evidence text here."

    mock_chat = AsyncMock()
    mock_chat.ainvoke.return_value = MagicMock(
        content=json.dumps([{"index": 0, "source_span": ""}])
    )

    mock_client = MagicMock(spec=LlmClient)
    mock_client.chat = mock_chat

    patched = await _patch_source_spans(edges, text, paper_id="p1", client=mock_client)
    assert patched[0].source_span is None


@pytest.mark.asyncio
async def test_patch_source_spans_falls_back_to_original_on_exception() -> None:
    edges = [_edge(edge_id="e1", edge_type="SUPPORTS", source_span=None)]

    mock_chat = AsyncMock()
    mock_chat.ainvoke.side_effect = Exception("LLM failure")

    mock_client = MagicMock(spec=LlmClient)
    mock_client.chat = mock_chat

    patched = await _patch_source_spans(edges, "text", paper_id="p1", client=mock_client)
    assert patched[0].source_span is None
    assert patched[0].rationale == "rationale"


@pytest.mark.asyncio
async def test_patch_source_spans_batches_large_sets() -> None:
    edges = [_edge(edge_id=f"e{i}", edge_type="SUPPORTS", source_span=None) for i in range(10)]
    text = "Verbatim sentence for all edges."

    mock_chat = AsyncMock()
    mock_chat.ainvoke.return_value = MagicMock(
        content=json.dumps(
            [{"index": i, "source_span": "Verbatim sentence for all edges."} for i in range(8)]
        )
    )

    mock_client = MagicMock(spec=LlmClient)
    mock_client.chat = mock_chat

    patched = await _patch_source_spans(edges, text, paper_id="p1", client=mock_client)
    assert mock_chat.ainvoke.call_count == 2
    assert sum(1 for e in patched if e.source_span) == 10
