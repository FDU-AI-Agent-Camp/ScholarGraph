# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for RAG indexing event handlers."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock

import pytest
from backend.rag.handlers import RAG_INDEX_WARNING_CODE, index_paper_for_rag
from backend.rag.models import PaperChunk, PaperEntity, PaperRelation
from backend.rag.vector_store import VectorStore
from backend.schemas.graph import GraphNode, NodeType, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm


class FakeVectorStore(VectorStore):
    """VectorStore stub that never talks to ChromaDB."""

    def __init__(self) -> None:
        self.indexed: dict[str, Any] = {}
        self.should_fail: Exception | None = None

    async def replace_paper_index(
        self,
        paper_id: str,
        *,
        chunks: list[PaperChunk],
        entities: list[PaperEntity],
        relations: list[PaperRelation],
    ) -> None:
        if self.should_fail is not None:
            raise self.should_fail
        self.indexed[paper_id] = {
            "chunks": chunks,
            "entities": entities,
            "relations": relations,
        }


@pytest.fixture
def sample_graph() -> UnifiedPaperGraph:
    return UnifiedPaperGraph(
        paper_id="paper-1",
        paradigm=Paradigm.STEM,
        nodes=[
            GraphNode(
                id="n_method",
                label="Hybrid chunker",
                type=NodeType.METHOD,
                data={},
            ),
        ],
        edges=[],
    )


@pytest.fixture
def mock_paper_service(monkeypatch: Any) -> MagicMock:
    service = MagicMock()
    service.record_extract_warnings = MagicMock()
    monkeypatch.setattr("backend.rag.handlers.get_paper_service", lambda: service)
    return service


@pytest.mark.asyncio
async def test_index_paper_for_rag_success_returns_true_and_indexes(
    sample_graph: UnifiedPaperGraph,
    mock_paper_service: MagicMock,
) -> None:
    store = FakeVectorStore()

    result = await index_paper_for_rag(
        "paper-1",
        full_text="Methods\nWe propose a hybrid chunker.",
        graph=sample_graph,
        vector_store=store,
    )

    assert result is True
    assert "paper-1" in store.indexed
    assert store.indexed["paper-1"]["chunks"]
    assert store.indexed["paper-1"]["entities"]
    mock_paper_service.record_extract_warnings.assert_not_called()


@pytest.mark.asyncio
async def test_index_paper_for_rag_passes_chunk_options_to_chunk_text(
    sample_graph: UnifiedPaperGraph,
    mock_paper_service: MagicMock,
    monkeypatch: Any,
) -> None:
    """All chunking configuration values must flow from settings into chunk_text."""

    from backend.config import Settings

    calls: list[dict[str, Any]] = []

    def fake_chunk_text(paper_id: str, full_text: str, **kwargs: Any) -> list[PaperChunk]:
        calls.append({"paper_id": paper_id, "full_text": full_text, **kwargs})
        return [
            PaperChunk(
                chunk_id=f"{paper_id}:chunk:0",
                paper_id=paper_id,
                text=full_text,
                section="methods",
                chunk_index=0,
                source="pymupdf",
                char_start=0,
                char_end=len(full_text),
            )
        ]

    monkeypatch.setattr("backend.rag.handlers.chunk_text", fake_chunk_text)

    settings = Settings.model_validate(
        {
            "embedding_provider": "openai",
            "rag_chunk_size_chars": 1000,
            "rag_chunk_overlap_ratio": 0.15,
            "rag_chunk_min_chunk_chars": 300,
            "rag_chunk_min_soft_boundary_window_chars": 250,
            "rag_chunk_include_references": True,
        }
    )
    monkeypatch.setattr("backend.config.get_settings", lambda: settings)

    await index_paper_for_rag(
        "paper-1",
        full_text="Methods\nWe propose a hybrid chunker.",
        graph=sample_graph,
        vector_store=FakeVectorStore(),
    )

    assert len(calls) == 1
    call = calls[0]
    assert call["paper_id"] == "paper-1"
    assert call["chunk_size_chars"] == 1000
    assert call["chunk_overlap_ratio"] == 0.15
    assert call["min_chunk_chars"] == 300
    assert call["min_soft_boundary_window_chars"] == 250
    assert call["include_references"] is True


@pytest.mark.asyncio
async def test_index_paper_for_rag_rejects_mismatched_graph_paper_id(
    sample_graph: UnifiedPaperGraph,
    mock_paper_service: MagicMock,
) -> None:
    store = FakeVectorStore()

    with pytest.raises(ValueError, match="graph.paper_id .* does not match paper_id"):
        await index_paper_for_rag(
            "paper-2",
            full_text="Methods\nWe propose a hybrid chunker.",
            graph=sample_graph,
            vector_store=store,
        )

    # Validation happens before any side effect; nothing should be indexed.
    assert not store.indexed
    mock_paper_service.record_extract_warnings.assert_not_called()


@pytest.mark.parametrize("invalid_paper_id", [None, "", "   ", 123])
@pytest.mark.asyncio
async def test_index_paper_for_rag_rejects_invalid_paper_id(
    invalid_paper_id: Any,
    sample_graph: UnifiedPaperGraph,
    mock_paper_service: MagicMock,
) -> None:
    store = FakeVectorStore()

    with pytest.raises(ValueError, match="paper_id must be a non-empty string"):
        await index_paper_for_rag(
            invalid_paper_id,  # type: ignore[arg-type]
            full_text="Methods\nWe propose a hybrid chunker.",
            graph=sample_graph,
            vector_store=store,
        )

    assert not store.indexed
    mock_paper_service.record_extract_warnings.assert_not_called()


@pytest.mark.asyncio
async def test_index_paper_for_rag_rejects_mismatched_graph_paper_id_variants(
    sample_graph: UnifiedPaperGraph,
    mock_paper_service: MagicMock,
) -> None:
    store = FakeVectorStore()

    mismatched_graph = UnifiedPaperGraph(
        paper_id="other-paper",
        paradigm=sample_graph.paradigm,
        nodes=list(sample_graph.nodes),
        edges=list(sample_graph.edges),
    )
    with pytest.raises(ValueError, match="graph.paper_id .* does not match paper_id"):
        await index_paper_for_rag(
            "paper-1",
            full_text="Methods\nWe propose a hybrid chunker.",
            graph=mismatched_graph,
            vector_store=store,
        )

    assert not store.indexed
    mock_paper_service.record_extract_warnings.assert_not_called()


@pytest.mark.asyncio
async def test_index_paper_for_rag_suppresses_error_and_records_warning(
    sample_graph: UnifiedPaperGraph,
    mock_paper_service: MagicMock,
    caplog: Any,
) -> None:
    store = FakeVectorStore()
    store.should_fail = RuntimeError("ChromaDB disk full")

    with caplog.at_level(logging.ERROR, logger="backend.rag.handlers"):
        result = await index_paper_for_rag(
            "paper-1",
            full_text="Methods\nWe propose a hybrid chunker.",
            graph=sample_graph,
            vector_store=store,
            suppress_errors=True,
        )

    assert result is False

    # Warning is surfaced on the paper status snapshot as a pure machine code.
    mock_paper_service.record_extract_warnings.assert_called_once()
    call_args = mock_paper_service.record_extract_warnings.call_args
    assert call_args.args[0] == "paper-1"
    assert call_args.args[1] == [RAG_INDEX_WARNING_CODE]

    # Structured log retains detailed error context for operators.
    assert any("rag_index_failed" in record.message for record in caplog.records)
    error_record = next(record for record in caplog.records if "rag_index_failed" in record.message)
    assert error_record.exc_info is not None
    assert error_record.paper_id == "paper-1"
    assert error_record.exc_type == "RuntimeError"
    assert "ChromaDB disk full" in error_record.exc_msg


@pytest.mark.asyncio
async def test_index_paper_for_rag_can_re_raise_when_suppress_disabled(
    sample_graph: UnifiedPaperGraph,
    mock_paper_service: MagicMock,
) -> None:
    store = FakeVectorStore()
    store.should_fail = ValueError("embedding failed")

    with pytest.raises(ValueError, match="embedding failed"):
        await index_paper_for_rag(
            "paper-1",
            full_text="Methods\nWe propose a hybrid chunker.",
            graph=sample_graph,
            vector_store=store,
            suppress_errors=False,
        )

    # Even when re-raising, the warning should still be recorded for observability.
    mock_paper_service.record_extract_warnings.assert_called_once()


@pytest.mark.asyncio
async def test_index_paper_for_rag_does_not_hide_warning_write_failure(
    sample_graph: UnifiedPaperGraph,
    mock_paper_service: MagicMock,
    caplog: Any,
) -> None:
    store = FakeVectorStore()
    store.should_fail = RuntimeError("ChromaDB disk full")
    mock_paper_service.record_extract_warnings.side_effect = OSError("DB unavailable")

    with caplog.at_level(logging.ERROR, logger="backend.rag.handlers"):
        result = await index_paper_for_rag(
            "paper-1",
            full_text="Methods\nWe propose a hybrid chunker.",
            graph=sample_graph,
            vector_store=store,
            suppress_errors=True,
        )

    assert result is False
    assert any("failed_to_record_rag_index_warning" in record.message for record in caplog.records)
