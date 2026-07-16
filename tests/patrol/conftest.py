"""Shared fixtures for patrol API and integration tests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
from backend.config import get_settings
from backend.llm.embeddings import get_embedding_client
from backend.main import app
from httpx import ASGITransport, AsyncClient

_PATROL_SETTING_ENV_KEYS: dict[str, str] = {
    "reranker_enabled": "RERANKER_ENABLED",
    "enable_patrol_semantic_path": "ENABLE_PATROL_SEMANTIC_PATH",
    "patrol_semantic_threshold": "PATROL_SEMANTIC_THRESHOLD",
    "patrol_max_matrix_size": "PATROL_MAX_MATRIX_SIZE",
    "patrol_topology_rq_semantic_threshold": "PATROL_TOPOLOGY_RQ_SEMANTIC_THRESHOLD",
    "patrol_topology_rq_semantic_threshold_english": "PATROL_TOPOLOGY_RQ_SEMANTIC_THRESHOLD_ENGLISH",
    "patrol_claim_rq_threshold": "PATROL_CLAIM_RQ_THRESHOLD",
    "patrol_claim_rq_coarse_threshold": "PATROL_CLAIM_RQ_COARSE_THRESHOLD",
    "patrol_claim_rq_rerank_threshold": "PATROL_RERANK_THRESHOLD",
    "patrol_claim_rq_threshold_english": "PATROL_CLAIM_RQ_THRESHOLD_ENGLISH",
    "patrol_claim_chunk_top_k": "PATROL_CLAIM_CHUNK_TOP_K",
}


def reset_patrol_runtime_caches() -> None:
    """Drop cached Settings / embedding / patrol service singletons."""
    get_settings.cache_clear()
    get_embedding_client.cache_clear()
    from backend.services.patrol_service import get_patrol_service

    if hasattr(get_patrol_service, "cache_clear"):
        get_patrol_service.cache_clear()


def patch_patrol_settings(monkeypatch: pytest.MonkeyPatch, **overrides: bool | int | float | str) -> None:
    """Override patrol-related settings via env vars and rebuild cached singletons."""
    for key, value in overrides.items():
        env_name = _PATROL_SETTING_ENV_KEYS[key]
        if isinstance(value, bool):
            monkeypatch.setenv(env_name, "true" if value else "false")
        else:
            monkeypatch.setenv(env_name, str(value))
    reset_patrol_runtime_caches()


_LIVE_PATROL_MARKERS = frozenset({"live_patrol_logic", "demo_profile_check"})


def _uses_live_patrol_settings(request: pytest.FixtureRequest) -> bool:
    return any(request.node.get_closest_marker(name) for name in _LIVE_PATROL_MARKERS)


@pytest.fixture(autouse=True)
def _enforce_golden_config_snapshot_for_live_patrol(
    request: pytest.FixtureRequest,
) -> Iterator[None]:
    """Block live_patrol_logic / demo_profile_check when config diverges from golden snapshot."""
    if not _uses_live_patrol_settings(request):
        yield
        return

    from tests.fixtures.patrol_golden_config_snapshot import validate_golden_config_snapshot

    validate_golden_config_snapshot()
    yield


@pytest.fixture(autouse=True)
def _isolate_patrol_settings(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> Iterator[None]:
    """Prevent cross-test Settings / embedding singleton pollution in patrol suite."""
    if _uses_live_patrol_settings(request):
        reset_patrol_runtime_caches()
        yield
        reset_patrol_runtime_caches()
        return

    monkeypatch.setenv("LLM_MODE", "mock")
    reset_patrol_runtime_caches()
    yield
    reset_patrol_runtime_caches()


@pytest.fixture(autouse=True)
def _disable_patrol_llm_unless_llm_tests(monkeypatch, request) -> None:
    """Avoid real LLM calls in patrol tests (fallback templates); test_llm_summary opts out."""
    if request.module.__name__.endswith(("test_llm_summary", "test_patrol_llm_integration")):
        return

    async def _no_llm(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr("backend.patrol.llm_summary.generate_patrol_summary", _no_llm)
    monkeypatch.setattr("backend.patrol.llm_summary.generate_method_overlap_summary", _no_llm)
    monkeypatch.setattr("backend.patrol.llm_summary.generate_claim_evolution_summary", _no_llm)
    monkeypatch.setattr("backend.patrol.lens_clash.generate_patrol_summary", _no_llm)
    monkeypatch.setattr("backend.patrol.contradiction.generate_patrol_summary", _no_llm)
    monkeypatch.setattr("backend.patrol.method_overlap.generate_method_overlap_summary", _no_llm)
    monkeypatch.setattr("backend.patrol.claim_evolution.generate_claim_evolution_summary", _no_llm)


@pytest.fixture(autouse=True)
def _patrol_service_with_mock_vector_store(monkeypatch) -> None:
    """Avoid real ChromaDB in patrol tests by returning a mock VectorStore."""
    from unittest.mock import AsyncMock

    from backend.rag import vector_store as rag_vs_module
    from backend.services import patrol_service as ps_module

    def _mock_vector_store(*_args, **_kwargs):
        mock = AsyncMock()
        mock.query_chunks.return_value = []
        return mock

    monkeypatch.setattr(rag_vs_module, "VectorStore", _mock_vector_store)

    original_get_patrol_service = ps_module.get_patrol_service

    def _mock_get_patrol_service():
        return ps_module.PatrolService(vector_store=_mock_vector_store())

    monkeypatch.setattr(ps_module, "get_patrol_service", _mock_get_patrol_service)
    if hasattr(original_get_patrol_service, "cache_clear"):
        original_get_patrol_service.cache_clear()


@pytest.fixture
def patrol_graph_dir(tmp_path, monkeypatch):
    """Isolated GRAPH_DATA_DIR with cleared settings cache."""
    graph_dir = tmp_path / "graphs"
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_dir))
    reset_patrol_runtime_caches()
    yield graph_dir
    reset_patrol_runtime_caches()


@pytest.fixture
async def api_client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def assert_api_envelope(body: dict) -> None:
    assert "data" in body
    assert "meta" in body
    assert isinstance(body["meta"].get("request_id"), str)
    assert body["meta"]["request_id"]
