# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Shared vector-store test doubles for protocol compliance and integration tests."""

from __future__ import annotations

import asyncio

from backend.rag.models import RetrievedChunk
from backend.rag.static_mock_vector_store import StaticMockVectorStore


def build_stem_and_hss_mock_chunks() -> dict[str, list[RetrievedChunk]]:
    """Fixture chunks for concurrent isolation: stem-001 indexed, hss-001 indexed."""
    base = StaticMockVectorStore.load_default()
    chunks_by_paper = dict(base._chunks_by_paper)
    chunks_by_paper["hss-001"] = [
        RetrievedChunk(
            id="mock:hss-001:hss-001:chunk:12",
            paper_id="hss-001",
            text="分论点通过路径依赖机制支撑核心论点，史料来自晚清通商口岸档案。",
            chunk_id="hss-001:chunk:12",
            chunk_index=12,
            char_start=0,
            char_end=30,
            page_start=4,
            source="mock_vector_store",
        ),
    ]
    return chunks_by_paper


class FlakyExistsVectorStore(StaticMockVectorStore):
    """Mock store that fails ``exists`` for the first *fail_count* probes, then recovers."""

    def __init__(
        self,
        *,
        fail_count: int = 1,
        fault: BaseException | None = None,
        chunks_by_paper: dict[str, list[RetrievedChunk]] | None = None,
    ) -> None:
        if chunks_by_paper is None:
            chunks_by_paper = build_stem_and_hss_mock_chunks()
        super().__init__(chunks_by_paper)
        if fail_count < 0:
            msg = "fail_count must be non-negative"
            raise ValueError(msg)
        self._remaining_failures = fail_count
        self._fault = fault or ConnectionError("transient connection refused")

    async def exists(self, paper_id: str) -> bool:
        if self._remaining_failures > 0:
            self._remaining_failures -= 1
            raise self._fault
        return await super().exists(paper_id)


class PaperScopedFaultVectorStore(StaticMockVectorStore):
    """Mock store that fails ``exists`` only for configured *paper_id* values."""

    def __init__(
        self,
        fault_paper_ids: frozenset[str],
        fault: BaseException | None = None,
        chunks_by_paper: dict[str, list[RetrievedChunk]] | None = None,
    ) -> None:
        if chunks_by_paper is None:
            chunks_by_paper = build_stem_and_hss_mock_chunks()
        super().__init__(chunks_by_paper)
        self._fault_paper_ids = fault_paper_ids
        self._fault = fault or ConnectionError("connection refused")

    async def exists(self, paper_id: str) -> bool:
        if paper_id in self._fault_paper_ids:
            raise self._fault
        return await super().exists(paper_id)


class ExistsFaultVectorStore(StaticMockVectorStore):
    """Mock store whose ``exists`` probe simulates vector-store infrastructure outage."""

    def __init__(
        self,
        fault: BaseException | None = None,
        chunks_by_paper: dict[str, list[RetrievedChunk]] | None = None,
    ) -> None:
        if chunks_by_paper is None:
            base = StaticMockVectorStore.load_default()
            chunks_by_paper = base._chunks_by_paper  # noqa: SLF001
        super().__init__(chunks_by_paper)
        self._exists_fault = fault or ConnectionError("connection refused")

    async def exists(self, paper_id: str) -> bool:
        raise self._exists_fault


class SlowGetChunkStore(StaticMockVectorStore):
    """Mock store whose L2 ``get_chunk_text`` exceeds the B10 preview latency gate."""

    def __init__(
        self,
        chunks_by_paper: dict[str, list[RetrievedChunk]] | None = None,
        *,
        delay_seconds: float = 0.5,
    ) -> None:
        if chunks_by_paper is None:
            base = StaticMockVectorStore.load_default()
            chunks_by_paper = base._chunks_by_paper  # noqa: SLF001
        super().__init__(chunks_by_paper)
        self._delay_seconds = delay_seconds

    async def get_chunk_text(self, paper_id: str, chunk_id: str) -> str | None:
        await asyncio.sleep(self._delay_seconds)
        return await super().get_chunk_text(paper_id, chunk_id)
