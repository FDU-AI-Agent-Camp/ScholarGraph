"""P9 fault-injection matrix, JSON Schema contracts, cache TTL, and multi-fault overlay."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from backend.patrol.circuit_breaker import CircuitState, VectorStoreCircuitBreaker
from backend.patrol.degradation import (
    PATROL_DEGRADED_CACHE_MAX_AGE_SECONDS,
    RAG_DEGRADED_META_KEY,
    legacy_meta_from_profile,
    make_degradation_profile,
    merge_degradation_profiles,
)
from backend.patrol.rag_service import PatrolRAGService, append_rag_degradation_notice
from backend.patrol.result_cache import (
    PATROL_HEALTHY_CACHE_MAX_AGE_SECONDS,
    InMemoryPatrolResultCache,
    build_patrol_cache_key,
)
from backend.schemas.patrol import (
    PatrolDegradationReason,
    PatrolDegradationSeverity,
    PatrolMode,
)
from backend.services.patrol_service import PatrolService
from httpx import ASGITransport, AsyncClient
from tests.fixtures.patrol_degradation_schema import assert_degradation_profile_contract
from tests.helpers.patrol_graphs import build_stem_graph_with_method_dataset
from tests.patrol.conftest import assert_api_envelope, reset_patrol_runtime_caches


class _FaultVectorStore:
    """Deterministic VectorStore stub for the three P9 critical points."""

    def __init__(
        self,
        *,
        exists_map: dict[str, bool] | None = None,
        exists_errors: dict[str, BaseException] | None = None,
        query_error: BaseException | None = None,
        query_chunks_by_paper: dict[str, list[Any]] | None = None,
    ) -> None:
        self.exists_map = exists_map or {}
        self.exists_errors = exists_errors or {}
        self.query_error = query_error
        self.query_chunks_by_paper = query_chunks_by_paper or {}
        self.exists_calls: list[str] = []
        self.query_calls: list[str] = []

    async def exists(self, paper_id: str) -> bool:
        self.exists_calls.append(paper_id)
        if paper_id in self.exists_errors:
            raise self.exists_errors[paper_id]
        return self.exists_map.get(paper_id, False)

    async def query_chunks(self, query: str, *, paper_id: str, top_k: int) -> list[Any]:
        self.query_calls.append(paper_id)
        if self.query_error is not None:
            raise self.query_error
        return list(self.query_chunks_by_paper.get(paper_id, []))


def _seed_method_overlap_graphs(graph_dir) -> None:
    from backend.graph.store import GraphStore

    store = GraphStore(base_dir=graph_dir)
    store.save(
        build_stem_graph_with_method_dataset(
            "stem-001",
            method_label="PCA",
            dataset_label="MNIST",
        ),
    )
    store.save(
        build_stem_graph_with_method_dataset(
            "stem-002",
            method_label="PCA",
            dataset_label="MNIST",
        ),
    )


def _install_patrol_service(monkeypatch, *, vector_store: Any, result_cache: Any | None = None) -> PatrolService:
    from backend.main import app
    from backend.services import patrol_service as ps_module

    service = PatrolService(
        vector_store=vector_store,
        result_cache=result_cache if result_cache is not None else InMemoryPatrolResultCache(),
        cache_enabled=True,
    )

    def _get_service() -> PatrolService:
        return service

    monkeypatch.setattr(ps_module, "get_patrol_service", _get_service)
    # FastAPI dependency override so route hits our injected service.
    from backend.api.routes import patrol as patrol_routes

    app.dependency_overrides[patrol_routes.get_patrol_service_dep] = _get_service
    reset_patrol_runtime_caches()
    return service


# ---------------------------------------------------------------------------
# Unit helpers (kept from prior suite)
# ---------------------------------------------------------------------------


def test_make_degradation_profile_sets_severity_and_papers() -> None:
    profile = make_degradation_profile(
        PatrolDegradationReason.INDEX_NOT_READY,
        ["stem-001", "stem-001", "stem-002"],
        timestamp=datetime(2026, 7, 13, 19, 15, tzinfo=UTC),
    )
    assert profile.reason_code == PatrolDegradationReason.INDEX_NOT_READY
    assert profile.severity == PatrolDegradationSeverity.WARNING
    assert profile.affected_papers == ["stem-001", "stem-002"]


def test_merge_prefers_vector_store_unavailable() -> None:
    index_missing = make_degradation_profile(PatrolDegradationReason.INDEX_NOT_READY, ["a"])
    store_down = make_degradation_profile(PatrolDegradationReason.VECTOR_STORE_UNAVAILABLE, ["b"])
    merged = merge_degradation_profiles(index_missing, store_down)
    assert merged is not None
    assert merged.reason_code == PatrolDegradationReason.VECTOR_STORE_UNAVAILABLE
    assert merged.affected_papers == ["a", "b"]
    assert merged.severity == PatrolDegradationSeverity.ERROR


def test_legacy_meta_mirrors_profile() -> None:
    profile = make_degradation_profile(PatrolDegradationReason.QUERY_FAILED, ["stem-001"])
    meta = legacy_meta_from_profile(profile)
    payload = meta[RAG_DEGRADED_META_KEY]
    assert isinstance(payload, dict)
    assert payload["reason"] == "query_failed"
    assert payload["reason_code"] == "QUERY_FAILED"
    assert payload["paper_ids"] == ["stem-001"]


def test_append_rag_degradation_notice_index_not_ready() -> None:
    summary = "两篇论文方法重叠分析完成。"
    meta = {RAG_DEGRADED_META_KEY: {"paper_ids": ["stem-001"], "reason": "index_not_ready"}}
    result = append_rag_degradation_notice(summary, meta)
    assert "向量索引尚未就绪" in result
    assert "stem-001" in result


def test_append_rag_degradation_notice_no_meta_unchanged() -> None:
    summary = "无降级。"
    assert append_rag_degradation_notice(summary, {}) == summary


def test_append_rag_degradation_notice_idempotent() -> None:
    meta = {RAG_DEGRADED_META_KEY: {"paper_ids": ["stem-001"], "reason": "index_not_ready"}}
    summary = append_rag_degradation_notice("完成。", meta)
    assert append_rag_degradation_notice(summary, meta) == summary


# ---------------------------------------------------------------------------
# Three-scenario API fault injection + schema contract
# ---------------------------------------------------------------------------


@pytest.mark.patrol_fault_injection
@pytest.mark.asyncio
async def test_rag_degradation_index_not_ready(
    monkeypatch: pytest.MonkeyPatch,
    patrol_graph_dir,
) -> None:
    """exists→False: HTTP 200 + INDEX_NOT_READY + structured_points without chunk dependency."""
    _seed_method_overlap_graphs(patrol_graph_dir)
    store = _FaultVectorStore(exists_map={"stem-001": False, "stem-002": False})
    _install_patrol_service(monkeypatch, vector_store=store)

    from backend.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/patrol",
            json={"paper_ids": ["stem-001", "stem-002"], "mode": "method_overlap"},
        )

    assert response.status_code == 200
    assert "max-age=60" in response.headers.get("cache-control", "")
    body = response.json()
    assert_api_envelope(body)
    insight = body["data"]["insights"][0]
    assert insight["is_degraded"] is True
    assert_degradation_profile_contract(insight["degradation_profile"])
    assert insight["degradation_profile"]["reason_code"] == "INDEX_NOT_READY"
    assert set(insight["degradation_profile"]["affected_papers"]) == {"stem-001", "stem-002"}
    assert isinstance(insight.get("structured_points"), list)
    assert len(insight["structured_points"]) >= 1
    assert store.query_calls == []

    app.dependency_overrides.clear()


@pytest.mark.patrol_fault_injection
@pytest.mark.asyncio
async def test_rag_degradation_query_timeout(
    monkeypatch: pytest.MonkeyPatch,
    patrol_graph_dir,
) -> None:
    """query_chunks TimeoutError: HTTP 200 + QUERY_FAILED (bubble, no process crash)."""
    _seed_method_overlap_graphs(patrol_graph_dir)
    store = _FaultVectorStore(
        exists_map={"stem-001": True, "stem-002": True},
        query_error=TimeoutError("vector query timed out"),
    )
    _install_patrol_service(monkeypatch, vector_store=store)

    from backend.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/patrol",
            json={"paper_ids": ["stem-001", "stem-002"], "mode": "method_overlap"},
        )

    assert response.status_code == 200
    insight = response.json()["data"]["insights"][0]
    assert insight["is_degraded"] is True
    assert_degradation_profile_contract(insight["degradation_profile"])
    assert insight["degradation_profile"]["reason_code"] == "QUERY_FAILED"
    assert set(insight["degradation_profile"]["affected_papers"]) >= {"stem-001", "stem-002"}
    assert store.query_calls  # query attempted then caught

    app.dependency_overrides.clear()


@pytest.mark.patrol_fault_injection
@pytest.mark.asyncio
async def test_rag_degradation_cluster_down(
    monkeypatch: pytest.MonkeyPatch,
    patrol_graph_dir,
) -> None:
    """ConnectionRefusedError: HTTP 200 + VECTOR_STORE_UNAVAILABLE (no process crash)."""
    _seed_method_overlap_graphs(patrol_graph_dir)
    store = _FaultVectorStore(
        exists_errors={
            "stem-001": ConnectionRefusedError("chroma refused"),
            "stem-002": ConnectionRefusedError("chroma refused"),
        },
    )
    _install_patrol_service(monkeypatch, vector_store=store)

    from backend.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/patrol",
            json={"paper_ids": ["stem-001", "stem-002"], "mode": "method_overlap"},
        )

    assert response.status_code == 200
    insight = response.json()["data"]["insights"][0]
    assert insight["is_degraded"] is True
    assert_degradation_profile_contract(insight["degradation_profile"])
    assert insight["degradation_profile"]["reason_code"] == "VECTOR_STORE_UNAVAILABLE"
    assert store.query_calls == []

    app.dependency_overrides.clear()


@pytest.mark.patrol_fault_injection
def test_degradation_profile_json_schema_rejects_null_and_missing_fields() -> None:
    import jsonschema

    with pytest.raises(AssertionError):
        assert_degradation_profile_contract(None)
    with pytest.raises(jsonschema.ValidationError):
        assert_degradation_profile_contract({"reason_code": "INDEX_NOT_READY"})


# ---------------------------------------------------------------------------
# Cache TTL transition (thin → thick) with injectable clock
# ---------------------------------------------------------------------------


@pytest.mark.patrol_fault_injection
@pytest.mark.asyncio
async def test_degraded_cache_ttl_truncated_then_refresh_after_expiry(
    monkeypatch: pytest.MonkeyPatch,
    patrol_graph_dir,
) -> None:
    """Degraded TTL=60s; after expiry + index ready, cache refreshes to thick TTL=24h."""
    _seed_method_overlap_graphs(patrol_graph_dir)
    clock = {"now": 0.0}

    def _clock() -> float:
        return clock["now"]

    cache = InMemoryPatrolResultCache(clock=_clock)
    store = _FaultVectorStore(exists_map={"stem-001": False, "stem-002": False})
    service = _install_patrol_service(monkeypatch, vector_store=store, result_cache=cache)

    from backend.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.post(
            "/api/v1/patrol",
            json={"paper_ids": ["stem-001", "stem-002"], "mode": "method_overlap"},
        )
        assert r1.status_code == 200
        assert r1.json()["data"]["insights"][0]["is_degraded"] is True

        key = build_patrol_cache_key(["stem-001", "stem-002"], PatrolMode.METHOD_OVERLAP)
        assert cache.inspect_ttl(key) == PATROL_DEGRADED_CACHE_MAX_AGE_SECONDS

        # T+10s: still cache hit (degraded)
        clock["now"] = 10.0
        r2 = await client.post(
            "/api/v1/patrol",
            json={"paper_ids": ["stem-001", "stem-002"], "mode": "method_overlap"},
        )
        assert r2.json()["data"]["insights"][0]["is_degraded"] is True
        exists_while_cached = len(store.exists_calls)

        # Flip index ready, advance past TTL
        store.exists_map = {"stem-001": True, "stem-002": True}
        store.query_chunks_by_paper = {
            "stem-001": [AsyncMock(text="chunk-a")],
            "stem-002": [AsyncMock(text="chunk-b")],
        }
        # Simplify: return empty chunks but no degradation when exists True
        store.query_error = None
        clock["now"] = 65.0

        r3 = await client.post(
            "/api/v1/patrol",
            json={"paper_ids": ["stem-001", "stem-002"], "mode": "method_overlap"},
        )

    assert r3.status_code == 200
    insight = r3.json()["data"]["insights"][0]
    assert insight["is_degraded"] is False
    assert insight.get("degradation_profile") in (None, {})
    assert cache.inspect_ttl(key) == PATROL_HEALTHY_CACHE_MAX_AGE_SECONDS
    assert len(store.exists_calls) > exists_while_cached
    _ = service

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Multi-fault overlay (pessimistic priority)
# ---------------------------------------------------------------------------


@pytest.mark.patrol_fault_injection
@pytest.mark.asyncio
async def test_multi_fault_overlay_prefers_vector_store_unavailable() -> None:
    """INDEX_NOT_READY on one paper + ConnectionRefused on probe merges to store down."""
    store = _FaultVectorStore(
        exists_map={"stem-001": False},
        exists_errors={"stem-002": ConnectionRefusedError("refused")},
    )
    service = PatrolRAGService(store)  # type: ignore[arg-type]
    _sections, profile = await service.enrich_context(
        PatrolMode.METHOD_OVERLAP,
        {"stem-001": "q1", "stem-002": "q2"},
        top_k=3,
    )
    assert profile is not None
    assert profile.reason_code == PatrolDegradationReason.VECTOR_STORE_UNAVAILABLE
    assert set(profile.affected_papers) >= {"stem-001", "stem-002"}


@pytest.mark.patrol_fault_injection
@pytest.mark.asyncio
async def test_multi_fault_index_missing_and_query_timeout_keeps_higher_priority() -> None:
    store = _FaultVectorStore(
        exists_map={"stem-001": False, "stem-002": True},
        query_error=TimeoutError("timed out"),
    )
    service = PatrolRAGService(store)  # type: ignore[arg-type]
    _sections, profile = await service.enrich_context(
        PatrolMode.METHOD_OVERLAP,
        {"stem-001": "q1", "stem-002": "q2"},
        top_k=3,
    )
    assert profile is not None
    # INDEX_NOT_READY (2) > QUERY_FAILED (1)
    assert profile.reason_code == PatrolDegradationReason.INDEX_NOT_READY
    assert "stem-001" in profile.affected_papers
    assert "stem-002" in profile.affected_papers


@pytest.mark.patrol_fault_injection
@pytest.mark.asyncio
async def test_circuit_breaker_opens_and_skips_subsequent_io() -> None:
    store = _FaultVectorStore(exists_errors={"stem-001": ConnectionRefusedError("down")})
    breaker = VectorStoreCircuitBreaker(failure_threshold=1, reset_timeout_seconds=30.0)
    service = PatrolRAGService(store, circuit_breaker=breaker)  # type: ignore[arg-type]

    _, profile1 = await service.enrich_context(PatrolMode.METHOD_OVERLAP, {"stem-001": "q"}, top_k=3)
    assert profile1 is not None
    assert profile1.reason_code == PatrolDegradationReason.VECTOR_STORE_UNAVAILABLE
    assert breaker.state == CircuitState.OPEN
    calls_after_open = len(store.exists_calls)

    _, profile2 = await service.enrich_context(PatrolMode.METHOD_OVERLAP, {"stem-001": "q"}, top_k=3)
    assert profile2 is not None
    assert profile2.reason_code == PatrolDegradationReason.VECTOR_STORE_UNAVAILABLE
    assert len(store.exists_calls) == calls_after_open  # no further I/O
