# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for PatrolRAGService exists probe and typed degradation bubbling."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from backend.patrol.circuit_breaker import CircuitState, VectorStoreCircuitBreaker
from backend.patrol.rag_service import PatrolRAGService
from backend.schemas.patrol import PatrolDegradationReason, PatrolMode


class _FakeVectorStore:
    def __init__(
        self,
        *,
        exists_map: dict[str, bool] | None = None,
        exists_errors: dict[str, BaseException] | None = None,
        query_error: BaseException | None = None,
        query_results: list[Any] | None = None,
    ) -> None:
        self.exists_map = exists_map or {}
        self.exists_errors = exists_errors or {}
        self.query_error = query_error
        self.query_results = query_results or []
        self.query_calls: list[tuple[str, str, int]] = []

    async def exists(self, paper_id: str) -> bool:
        if paper_id in self.exists_errors:
            raise self.exists_errors[paper_id]
        return self.exists_map.get(paper_id, False)

    async def query_chunks(self, query: str, *, paper_id: str, top_k: int) -> list[Any]:
        self.query_calls.append((query, paper_id, top_k))
        if self.query_error is not None:
            raise self.query_error
        return list(self.query_results[:top_k])


@pytest.mark.asyncio
async def test_enrich_context_skips_query_when_index_missing() -> None:
    store = _FakeVectorStore(exists_map={"stem-001": False, "stem-002": True})
    service = PatrolRAGService(store)  # type: ignore[arg-type]
    sections, profile = await service.enrich_context(
        PatrolMode.METHOD_OVERLAP,
        {"stem-001": "q1", "stem-002": "q2"},
        top_k=3,
    )
    assert sections == []
    assert profile is not None
    assert profile.reason_code == PatrolDegradationReason.INDEX_NOT_READY
    assert profile.affected_papers == ["stem-001"]
    assert [paper_id for _, paper_id, _ in store.query_calls] == ["stem-002"]


@pytest.mark.asyncio
async def test_enrich_context_marks_vector_store_unavailable_on_connection_error() -> None:
    store = _FakeVectorStore(exists_errors={"stem-001": ConnectionError("refused")})
    service = PatrolRAGService(store)  # type: ignore[arg-type]
    _, profile = await service.enrich_context(
        PatrolMode.METHOD_OVERLAP,
        {"stem-001": "q"},
        top_k=3,
    )
    assert profile is not None
    assert profile.reason_code == PatrolDegradationReason.VECTOR_STORE_UNAVAILABLE
    assert store.query_calls == []


@pytest.mark.asyncio
async def test_enrich_context_marks_query_timeout_as_query_failed() -> None:
    store = _FakeVectorStore(exists_map={"stem-001": True}, query_error=TimeoutError("timed out"))
    service = PatrolRAGService(store)  # type: ignore[arg-type]
    _, profile = await service.enrich_context(
        PatrolMode.METHOD_OVERLAP,
        {"stem-001": "q"},
        top_k=3,
    )
    assert profile is not None
    assert profile.reason_code == PatrolDegradationReason.QUERY_FAILED


@pytest.mark.asyncio
async def test_enrich_context_marks_query_failed() -> None:
    store = _FakeVectorStore(exists_map={"stem-001": True}, query_error=RuntimeError("boom"))
    service = PatrolRAGService(store)  # type: ignore[arg-type]
    _, profile = await service.enrich_context(
        PatrolMode.METHOD_OVERLAP,
        {"stem-001": "q"},
        top_k=3,
    )
    assert profile is not None
    assert profile.reason_code == PatrolDegradationReason.QUERY_FAILED


@pytest.mark.asyncio
async def test_enrich_context_without_vector_store() -> None:
    service = PatrolRAGService(None)
    sections, profile = await service.enrich_context(
        PatrolMode.CLAIM_EVOLUTION,
        {"a": "q", "b": "q"},
    )
    assert sections == []
    assert profile is not None
    assert profile.reason_code == PatrolDegradationReason.VECTOR_STORE_UNAVAILABLE
    assert set(profile.affected_papers) == {"a", "b"}


@pytest.mark.asyncio
async def test_retrieve_backfill_chunks_returns_empty_when_circuit_open() -> None:
    store = _FakeVectorStore(exists_map={"stem-001": True})
    breaker = VectorStoreCircuitBreaker(failure_threshold=1)
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    service = PatrolRAGService(store, circuit_breaker=breaker)  # type: ignore[arg-type]

    chunks, profile = await service.retrieve_backfill_chunks("stem-001", "Q1", top_k=3)

    assert chunks == []
    assert profile is not None
    assert profile.reason_code == PatrolDegradationReason.VECTOR_STORE_UNAVAILABLE
    assert profile.affected_papers == ["stem-001"]
    assert store.query_calls == []


@pytest.mark.asyncio
async def test_retrieve_backfill_chunks_skips_query_when_index_missing() -> None:
    store = _FakeVectorStore(exists_map={"stem-001": False})
    service = PatrolRAGService(store)  # type: ignore[arg-type]

    chunks, profile = await service.retrieve_backfill_chunks("stem-001", "Q1", top_k=3)

    assert chunks == []
    assert profile is not None
    assert profile.reason_code == PatrolDegradationReason.INDEX_NOT_READY
    assert store.query_calls == []


@pytest.mark.asyncio
async def test_retrieve_backfill_chunks_maps_timeout_to_query_failed() -> None:
    store = _FakeVectorStore(exists_map={"stem-001": True}, query_error=TimeoutError("timed out"))
    service = PatrolRAGService(store)  # type: ignore[arg-type]

    chunks, profile = await service.retrieve_backfill_chunks("stem-001", "Q1", top_k=3)

    assert chunks == []
    assert profile is not None
    assert profile.reason_code == PatrolDegradationReason.QUERY_FAILED
    assert store.query_calls == [("Q1", "stem-001", 3)]


@pytest.mark.asyncio
async def test_retrieve_backfill_chunks_trips_breaker_on_connection_error() -> None:
    store = _FakeVectorStore(
        exists_map={"stem-001": True},
        query_error=ConnectionError("connection refused"),
    )
    breaker = VectorStoreCircuitBreaker(failure_threshold=1)
    service = PatrolRAGService(store, circuit_breaker=breaker)  # type: ignore[arg-type]

    chunks, profile = await service.retrieve_backfill_chunks("stem-001", "Q1", top_k=3)

    assert chunks == []
    assert profile is not None
    assert profile.reason_code == PatrolDegradationReason.VECTOR_STORE_UNAVAILABLE
    assert breaker.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_retrieve_backfill_chunks_returns_stripped_texts_on_success() -> None:
    store = _FakeVectorStore(
        exists_map={"stem-001": True},
        query_results=[
            SimpleNamespace(text="  keep me  "),
            SimpleNamespace(text="   "),
            SimpleNamespace(text="also keep"),
        ],
    )
    service = PatrolRAGService(store)  # type: ignore[arg-type]

    chunks, profile = await service.retrieve_backfill_chunks("stem-001", "Q1", top_k=5)

    assert chunks == ["keep me", "also keep"]
    assert profile is None
    assert store.query_calls == [("Q1", "stem-001", 5)]
    assert service.circuit_breaker.state == CircuitState.CLOSED
