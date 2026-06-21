"""Tests for chunk-level retry and isolation in extract_chunked (Slice 2)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from backend.agents.extract_chunked import extract_chunked
from backend.config import Settings
from backend.schemas.extract_phase import ExtractedEdgeList, ExtractedNodeList
from backend.schemas.paper import PaperDetail, PaperStatus, PaperStatusData, PipelineStage
from backend.schemas.paradigm import Paradigm
from backend.services.paper_service import get_paper_service


def _settings(retry_attempts: int = 3, retry_delay: float = 0.0) -> Settings:
    return Settings(
        _env_file=None,
        llm_mode="mock",
        extract_chunk_retry_attempts=retry_attempts,
        extract_chunk_retry_delay_s=retry_delay,
    )


def _register_paper(paper_id: str) -> None:
    service = get_paper_service()
    now = datetime.now(UTC)
    service._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="retry test",
        status=PaperStatus.PROCESSING,
        created_at=now,
        updated_at=now,
    )
    service._status[paper_id] = PaperStatusData(
        paper_id=paper_id,
        status=PaperStatus.PROCESSING,
        percent=50,
        stage=PipelineStage.EXTRACTING,
        message="extracting",
        updated_at=now,
    )


def _node_list(count: int) -> ExtractedNodeList:
    from backend.schemas.extract_phase import ExtractedNode

    return ExtractedNodeList(
        paradigm=Paradigm.HSS,
        nodes=[ExtractedNode(id=f"n{i}", label=f"N{i}", type="Thesis") for i in range(count)],
    )


def _edge_list(count: int, source: str = "c0_n0", target: str = "c0_n1") -> ExtractedEdgeList:
    from backend.schemas.extract_phase import ExtractedEdge

    return ExtractedEdgeList(
        paradigm=Paradigm.HSS,
        nodes=[],
        edges=[
            ExtractedEdge(
                id=f"e{i}",
                source=source,
                target=target,
                label="supports",
                type="SUPPORTS",
            )
            for i in range(count)
        ],
    )


@pytest.fixture(autouse=True)
def _fresh_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "mock")
    from backend.config import get_settings
    from backend.services.paper_service import get_paper_service

    get_settings.cache_clear()
    get_paper_service.cache_clear()
    yield
    get_paper_service.cache_clear()


class TestChunkRetry:
    async def test_retries_failed_node_extraction_then_succeeds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        paper_id = "retry-001"
        _register_paper(paper_id)
        settings = _settings(retry_attempts=3, retry_delay=0.0)

        call_count = 0

        async def flaky_extract_nodes(*args, **kwargs) -> ExtractedNodeList:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("truncated json")
            return _node_list(2)

        monkeypatch.setattr("backend.agents.extract_chunked.extract_nodes_with_llm", flaky_extract_nodes)
        monkeypatch.setattr(
            "backend.agents.extract_chunked.build_edges_with_llm",
            AsyncMock(return_value=_edge_list(1)),
        )
        monkeypatch.setattr(
            "backend.agents.extract_chunked.get_extract_rate_limiter",
            lambda: MagicMock(acquire=AsyncMock()),
        )

        result = await extract_chunked("x" * 50_000, Paradigm.HSS, paper_id=paper_id, settings=settings)
        assert call_count == 3
        assert len(result.nodes) == 2

    async def test_chunk_isolation_allows_other_chunks_to_succeed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        paper_id = "iso-001"
        _register_paper(paper_id)
        settings = _settings(retry_attempts=1, retry_delay=0.0)

        def _two_chunks(text: str, paradigm: Paradigm, *, max_chunk_chars: int) -> list:
            _ = text, paradigm, max_chunk_chars
            from backend.ingest.chunking import TextChunk

            return [
                TextChunk(index=0, text="chunk0", title="t0", start_char=0, end_char=6),
                TextChunk(index=1, text="chunk1", title="t1", start_char=6, end_char=12),
            ]

        monkeypatch.setattr("backend.agents.extract_chunked.chunk_text", _two_chunks)
        monkeypatch.setattr(
            "backend.agents.extract_chunked.get_extract_rate_limiter",
            lambda: MagicMock(acquire=AsyncMock()),
        )

        async def selective_extract_nodes(prompt: str, *args, **kwargs) -> ExtractedNodeList:
            if "chunk0" in prompt:
                raise RuntimeError("chunk 0 always fails")
            return _node_list(2)

        async def selective_build_edges(*args, **kwargs) -> ExtractedEdgeList:
            prompt = args[1] if len(args) > 1 else kwargs.get("prompt", "")
            if "chunk0" in prompt:
                return _edge_list(1, source="c0_n0", target="c0_n1")
            return _edge_list(1, source="c1_n0", target="c1_n1")

        monkeypatch.setattr("backend.agents.extract_chunked.extract_nodes_with_llm", selective_extract_nodes)
        monkeypatch.setattr(
            "backend.agents.extract_chunked.build_edges_with_llm",
            AsyncMock(side_effect=selective_build_edges),
        )

        result = await extract_chunked("x" * 50_000, Paradigm.HSS, paper_id=paper_id, settings=settings)

        assert len(result.nodes) == 2
        assert any("chunk_0_node_extraction_failed" in w for w in result.warnings)

    async def test_all_node_chunks_failing_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        paper_id = "iso-002"
        _register_paper(paper_id)
        settings = _settings(retry_attempts=1, retry_delay=0.0)

        monkeypatch.setattr(
            "backend.agents.extract_chunked.extract_nodes_with_llm",
            AsyncMock(side_effect=RuntimeError("boom")),
        )
        monkeypatch.setattr(
            "backend.agents.extract_chunked.get_extract_rate_limiter",
            lambda: MagicMock(acquire=AsyncMock()),
        )

        with pytest.raises(ValueError, match="empty node lists"):
            await extract_chunked("x" * 50_000, Paradigm.HSS, paper_id=paper_id, settings=settings)


class TestChunkSettings:
    async def test_retry_attempts_zero_disables_retry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        paper_id = "retry-off-001"
        _register_paper(paper_id)
        settings = _settings(retry_attempts=0, retry_delay=0.0)

        call_count = 0

        async def always_fail(*args, **kwargs) -> ExtractedNodeList:
            nonlocal call_count
            call_count += 1
            raise ValueError("fail")

        monkeypatch.setattr("backend.agents.extract_chunked.extract_nodes_with_llm", always_fail)
        monkeypatch.setattr(
            "backend.agents.extract_chunked.get_extract_rate_limiter",
            lambda: MagicMock(acquire=AsyncMock()),
        )

        with pytest.raises(ValueError, match="empty node lists"):
            await extract_chunked("x" * 50_000, Paradigm.HSS, paper_id=paper_id, settings=settings)

        assert call_count == 1
