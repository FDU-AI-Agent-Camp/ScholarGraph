"""Tests for chunked extraction rate limiting and chunk cap removal (Slice 2)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.agents.extract_chunked import extract_chunked
from backend.config import Settings
from backend.llm.rate_limiter import AsyncTokenBucket
from backend.schemas.extract_phase import ExtractedEdgeList, ExtractedNodeList
from backend.schemas.paradigm import Paradigm


def _node_list(n: int) -> ExtractedNodeList:
    from backend.schemas.extract_phase import ExtractedNode

    return ExtractedNodeList(
        paradigm=Paradigm.HSS,
        nodes=[ExtractedNode(id=f"n{i}", label=f"Node {i}", type="Thesis") for i in range(n)],
    )


def _edge_list(n: int) -> ExtractedEdgeList:
    from backend.schemas.extract_phase import ExtractedEdge

    return ExtractedEdgeList(
        paradigm=Paradigm.HSS,
        edges=[
            ExtractedEdge(
                id=f"e{i}",
                source=f"n{i}",
                target=f"n{i}",
                label="REF",
                type="REF",
            )
            for i in range(n)
        ],
    )


def _graph_result(paper_id: str, node_count: int = 1) -> object:
    from backend.schemas.extract_phase import ExtractedGraph, ExtractedNode

    return ExtractedGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[ExtractedNode(id=f"n{i}", label=f"Node {i}", type="Thesis") for i in range(node_count)],
        edges=[],
        summary="mock",
    )


@pytest.fixture(autouse=True)
def _fresh_limiter(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.config import get_settings
    from backend.llm.rate_limiter import reset_extract_rate_limiter

    monkeypatch.setenv("LLM_MODE", "mock")
    get_settings.cache_clear()
    reset_extract_rate_limiter()
    yield
    reset_extract_rate_limiter()


class TestExtractChunkedRateLimit:
    async def test_acquires_rate_limit_before_each_llm_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        paper_id = "rl-001"
        full_text = "x"

        def _five_chunks(text: str, paradigm: Paradigm, *, max_chunk_chars: int) -> list:
            _ = text, paradigm, max_chunk_chars
            from backend.ingest.chunking import TextChunk

            return [TextChunk(index=i, text=f"chunk{i}", title="t", start_char=i, end_char=i + 1) for i in range(5)]

        monkeypatch.setattr("backend.agents.extract_chunked.chunk_text", _five_chunks)

        acquired: list[int] = []
        real_limiter = AsyncTokenBucket(rpm=1000, tpm=1_000_000)

        async def _tracked_acquire(*, tokens: int = 1, chars: int = 0) -> None:
            acquired.append(chars)
            await real_limiter.acquire(tokens=tokens, chars=chars)

        fake_limiter = MagicMock()
        fake_limiter.acquire = _tracked_acquire
        monkeypatch.setattr("backend.agents.extract_chunked.get_extract_rate_limiter", lambda: fake_limiter)

        with (
            patch("backend.agents.extract_chunked.extract_nodes_with_llm", new=AsyncMock(return_value=_node_list(1))),
            patch("backend.agents.extract_chunked.build_edges_with_llm", new=AsyncMock(return_value=_edge_list(1))),
            patch("backend.agents.extract_chunked.merge_graphs", new=MagicMock(return_value=_graph_result(paper_id))),
        ):
            await extract_chunked(full_text, Paradigm.HSS, paper_id=paper_id)

        # Two acquires per chunk: one for node extraction, one for edge extraction.
        assert len(acquired) == 10
        assert all(chars > 0 for chars in acquired)

    async def test_does_not_hard_cap_at_old_max_chunks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        paper_id = "rl-002"
        full_text = "x"

        def _many_chunks(text: str, paradigm: Paradigm, *, max_chunk_chars: int) -> list:
            _ = text, paradigm, max_chunk_chars
            from backend.ingest.chunking import TextChunk

            return [TextChunk(index=i, text=f"chunk{i}", title="t", start_char=i, end_char=i + 1) for i in range(25)]

        monkeypatch.setattr("backend.agents.extract_chunked.chunk_text", _many_chunks)

        with (
            patch("backend.agents.extract_chunked.extract_nodes_with_llm", new=AsyncMock(return_value=_node_list(1))),
            patch("backend.agents.extract_chunked.build_edges_with_llm", new=AsyncMock(return_value=_edge_list(1))),
            patch("backend.agents.extract_chunked.merge_graphs", new=MagicMock(return_value=_graph_result(paper_id, node_count=25))),
        ):
            result = await extract_chunked(full_text, Paradigm.HSS, paper_id=paper_id)

        # Old cap was 10; new default cap is 1000, so all 25 chunks should be processed.
        assert len(result.nodes) == 25

    async def test_chunk_count_exceeds_safety_limit_truncates(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        paper_id = "rl-003"
        full_text = "x"

        def _many_chunks(text: str, paradigm: Paradigm, *, max_chunk_chars: int) -> list:
            _ = text, paradigm, max_chunk_chars
            from backend.ingest.chunking import TextChunk

            return [TextChunk(index=i, text=f"chunk{i}", title="t", start_char=i, end_char=i + 1) for i in range(25)]

        monkeypatch.setattr("backend.agents.extract_chunked.chunk_text", _many_chunks)

        settings = Settings(
            _env_file=None,
            llm_mode="mock",
            extract_chunk_max_chunks=10,
        )

        processed_chunks: list[int] = []

        async def tracked_extract_nodes(prompt: str, paradigm: Paradigm, *, paper_id: str, **kwargs) -> ExtractedNodeList:
            processed_chunks.append(len(processed_chunks))
            return _node_list(1)

        with (
            patch("backend.agents.extract_chunked.extract_nodes_with_llm", new=AsyncMock(side_effect=tracked_extract_nodes)),
            patch("backend.agents.extract_chunked.build_edges_with_llm", new=AsyncMock(return_value=_edge_list(1))),
            patch("backend.agents.extract_chunked.merge_graphs", new=MagicMock(return_value=_graph_result(paper_id, node_count=10))),
        ):
            await extract_chunked(full_text, Paradigm.HSS, paper_id=paper_id, settings=settings)

        assert len(processed_chunks) == 10

    async def test_semaphore_limits_concurrent_llm_calls(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        paper_id = "rl-004"
        full_text = "x"

        def _ten_chunks(text: str, paradigm: Paradigm, *, max_chunk_chars: int) -> list:
            _ = text, paradigm, max_chunk_chars
            from backend.ingest.chunking import TextChunk

            return [TextChunk(index=i, text=f"chunk{i}", title="t", start_char=i, end_char=i + 1) for i in range(10)]

        monkeypatch.setattr("backend.agents.extract_chunked.chunk_text", _ten_chunks)

        settings = Settings(
            _env_file=None,
            llm_mode="mock",
            extract_chunk_concurrency=2,
        )

        concurrent = 0
        max_concurrent = 0
        lock = asyncio.Lock()

        async def slow_extract_nodes(*args, **kwargs) -> ExtractedNodeList:
            nonlocal concurrent, max_concurrent
            async with lock:
                concurrent += 1
                max_concurrent = max(max_concurrent, concurrent)
            await asyncio.sleep(0.05)
            async with lock:
                concurrent -= 1
            return _node_list(1)

        async def slow_build_edges(*args, **kwargs) -> ExtractedEdgeList:
            await asyncio.sleep(0.01)
            return _edge_list(1)

        monkeypatch.setattr("backend.agents.extract_chunked.get_extract_rate_limiter", lambda: MagicMock(acquire=AsyncMock()))

        with (
            patch("backend.agents.extract_chunked.extract_nodes_with_llm", new=AsyncMock(side_effect=slow_extract_nodes)),
            patch("backend.agents.extract_chunked.build_edges_with_llm", new=AsyncMock(side_effect=slow_build_edges)),
            patch("backend.agents.extract_chunked.merge_graphs", new=MagicMock(return_value=_graph_result(paper_id, node_count=10))),
        ):
            await extract_chunked(full_text, Paradigm.HSS, paper_id=paper_id, settings=settings)

        assert max_concurrent <= 2

    async def test_empty_node_lists_raises_value_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        paper_id = "rl-005"
        full_text = "x"

        def _two_chunks(text: str, paradigm: Paradigm, *, max_chunk_chars: int) -> list:
            _ = text, paradigm, max_chunk_chars
            from backend.ingest.chunking import TextChunk

            return [TextChunk(index=i, text=f"chunk{i}", title="t", start_char=i, end_char=i + 1) for i in range(2)]

        monkeypatch.setattr("backend.agents.extract_chunked.chunk_text", _two_chunks)
        monkeypatch.setattr("backend.agents.extract_chunked.get_extract_rate_limiter", lambda: MagicMock(acquire=AsyncMock()))

        empty_nodes = ExtractedNodeList.model_construct(paradigm=Paradigm.HSS, nodes=[])

        with (
            patch("backend.agents.extract_chunked.extract_nodes_with_llm", new=AsyncMock(return_value=empty_nodes)),
            patch("backend.agents.extract_chunked.build_edges_with_llm", new=AsyncMock(return_value=_edge_list(0))),
            pytest.raises(ValueError, match="empty node lists"),
        ):
            await extract_chunked(full_text, Paradigm.HSS, paper_id=paper_id)
