"""Red-light / robustness tests for RAG indexing handlers.

These tests intentionally break dependencies to verify that
``index_paper_for_rag`` fails gracefully and produces useful feedback.
Every test uses an isolated temporary Chroma directory to avoid polluting
``./data/chroma`` or any other default persistence path.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from backend.rag.handlers import RAG_INDEX_WARNING_CODE, index_paper_for_rag
from backend.rag.models import PaperChunk, PaperEntity, PaperRelation
from backend.rag.vector_store import VectorStore
from backend.schemas.graph import GraphNode, NodeType, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm


class FailingEmbeddingClient:
    async def embed_texts(self, _texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embedding service unreachable")


class FailingVectorStore(VectorStore):
    async def replace_paper_index(
        self,
        paper_id: str,
        *,
        chunks: list[PaperChunk],
        entities: list[PaperEntity],
        relations: list[PaperRelation],
    ) -> None:
        raise ConnectionError("ChromaDB connection refused")


@pytest.fixture
def tmp_chroma_path(tmp_path: Path) -> str:
    """Provide an isolated Chroma persistence directory per test."""
    return str(tmp_path / "chroma_test_dir")


@pytest.fixture
def sample_graph() -> UnifiedPaperGraph:
    return UnifiedPaperGraph(
        paper_id="paper-1",
        paradigm=Paradigm.STEM,
        nodes=[GraphNode(id="n_1", label="Claim", type=NodeType.CLAIM, data={})],
        edges=[],
    )


@pytest.fixture
def mock_paper_service(monkeypatch: Any) -> MagicMock:
    service = MagicMock()
    service.record_extract_warnings = MagicMock()
    monkeypatch.setattr("backend.rag.handlers.get_paper_service", lambda: service)
    return service


@pytest.mark.asyncio
async def test_embedding_failure_is_suppressed_and_recorded(
    sample_graph: UnifiedPaperGraph,
    mock_paper_service: MagicMock,
    tmp_chroma_path: str,
    caplog: Any,
) -> None:
    store = VectorStore(embedding_client=FailingEmbeddingClient(), chroma_path=tmp_chroma_path)

    with caplog.at_level(logging.ERROR, logger="backend.rag.handlers"):
        result = await index_paper_for_rag(
            "paper-1",
            full_text="Methods\nWe do something.",
            graph=sample_graph,
            vector_store=store,
            suppress_errors=True,
        )

    assert result is False
    mock_paper_service.record_extract_warnings.assert_called_once()
    warning = mock_paper_service.record_extract_warnings.call_args.args[1][0]
    assert RAG_INDEX_WARNING_CODE in warning
    assert "RuntimeError" in warning
    assert "embedding service unreachable" in warning

    error_record = next(record for record in caplog.records if RAG_INDEX_WARNING_CODE in record.message)
    assert error_record.exc_type == "RuntimeError"


@pytest.mark.asyncio
async def test_vector_store_failure_is_suppressed_and_recorded(
    sample_graph: UnifiedPaperGraph,
    mock_paper_service: MagicMock,
    tmp_chroma_path: str,
    caplog: Any,
) -> None:
    store = FailingVectorStore(embedding_client=MagicMock(), chroma_path=tmp_chroma_path)

    with caplog.at_level(logging.ERROR, logger="backend.rag.handlers"):
        result = await index_paper_for_rag(
            "paper-1",
            full_text="Methods\nWe do something.",
            graph=sample_graph,
            vector_store=store,
            suppress_errors=True,
        )

    assert result is False
    warning = mock_paper_service.record_extract_warnings.call_args.args[1][0]
    assert "ConnectionError" in warning
    assert "ChromaDB connection refused" in warning


@pytest.mark.asyncio
async def test_suppress_false_re_raises_with_full_stack(
    sample_graph: UnifiedPaperGraph,
    mock_paper_service: MagicMock,
    tmp_chroma_path: str,
) -> None:
    store = VectorStore(embedding_client=FailingEmbeddingClient(), chroma_path=tmp_chroma_path)

    with pytest.raises(RuntimeError, match="embedding service unreachable"):
        await index_paper_for_rag(
            "paper-1",
            full_text="Methods\nWe do something.",
            graph=sample_graph,
            vector_store=store,
            suppress_errors=False,
        )

    # Warning should still be recorded before re-raising.
    mock_paper_service.record_extract_warnings.assert_called_once()


@pytest.mark.asyncio
async def test_empty_full_text_is_allowed_and_indexes_empty_chunks(
    sample_graph: UnifiedPaperGraph,
    mock_paper_service: MagicMock,
    tmp_chroma_path: str,
    caplog: Any,
) -> None:
    # MagicMock embedding returns empty list by default, causing count mismatch.
    # Use a real fake to keep the happy path working.
    from tests.integration.test_rag_vector_store import FakeEmbeddingClient

    store = VectorStore(embedding_client=FakeEmbeddingClient(), chroma_path=tmp_chroma_path)

    result = await index_paper_for_rag(
        "paper-1",
        full_text="",
        graph=sample_graph,
        vector_store=store,
        suppress_errors=True,
    )

    assert result is True
    mock_paper_service.record_extract_warnings.assert_not_called()


@pytest.mark.asyncio
async def test_warning_write_failure_does_not_hide_original_error(
    sample_graph: UnifiedPaperGraph,
    mock_paper_service: MagicMock,
    tmp_chroma_path: str,
    caplog: Any,
) -> None:
    mock_paper_service.record_extract_warnings.side_effect = OSError("DB down")
    store = VectorStore(embedding_client=FailingEmbeddingClient(), chroma_path=tmp_chroma_path)

    with caplog.at_level(logging.ERROR, logger="backend.rag.handlers"):
        result = await index_paper_for_rag(
            "paper-1",
            full_text="Methods\nWe do something.",
            graph=sample_graph,
            vector_store=store,
            suppress_errors=True,
        )

    assert result is False
    assert any("failed_to_record_rag_index_warning" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_exception_message_is_truncated_in_warning(
    sample_graph: UnifiedPaperGraph,
    mock_paper_service: MagicMock,
    tmp_chroma_path: str,
) -> None:
    class LongMessageError(Exception):
        pass

    class BoomEmbeddingClient:
        async def embed_texts(self, _texts: list[str]) -> list[list[float]]:
            raise LongMessageError("x" * 500)

    store = VectorStore(embedding_client=BoomEmbeddingClient(), chroma_path=tmp_chroma_path)

    await index_paper_for_rag(
        "paper-1",
        full_text="Methods\nWe do something.",
        graph=sample_graph,
        vector_store=store,
        suppress_errors=True,
    )

    warning = mock_paper_service.record_extract_warnings.call_args.args[1][0]
    assert len(warning) <= 200
    assert warning.endswith("...")
