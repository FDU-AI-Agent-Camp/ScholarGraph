# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Shared pytest fixtures for cross-package tests."""

from __future__ import annotations

import importlib.util
import os

# Keep unit tests independent of developer ``.env`` (LLM_MODE=live, custom models, etc.).
os.environ.setdefault("SCHOLARGRAPH_IGNORE_DOTENV", "1")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("APP_PROFILE", "ci")
os.environ.setdefault("STARTUP_RERANKER_PROBE", "false")
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.config import get_settings

from tests.helpers.persistence_testkit import init_isolated_database, reset_persistence_singletons

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_PIPELINE_SCRIPT = REPO_ROOT / "scripts" / "run_pipeline.py"
RUN_PATROL_SCRIPT = REPO_ROOT / "scripts" / "run_patrol.py"
BENCHMARK_DUAL_ROUTE_SCRIPT = REPO_ROOT / "scripts" / "benchmark_dual_route.py"
BENCHMARK_REGRESSION_SCRIPT = REPO_ROOT / "scripts" / "benchmark_regression.py"


@pytest.fixture
def run_pipeline_module():
    """Load scripts/run_pipeline.py as a module (not installed as package)."""
    spec = importlib.util.spec_from_file_location("run_pipeline", RUN_PIPELINE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def run_patrol_module():
    """Load scripts/run_patrol.py as a module (not installed as package)."""
    spec = importlib.util.spec_from_file_location("run_patrol", RUN_PATROL_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def benchmark_regression_module():
    """Load scripts/benchmark_regression.py as a module (not installed as package)."""
    import sys

    spec = importlib.util.spec_from_file_location("benchmark_regression", BENCHMARK_REGRESSION_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def benchmark_dual_route_module():
    """Load scripts/benchmark_dual_route.py as a module (not installed as package)."""
    import sys

    spec = importlib.util.spec_from_file_location("benchmark_dual_route", BENCHMARK_DUAL_ROUTE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Cached after session warm-up so function-scoped fixtures avoid re-importing FastAPI app.
_SESSION_APP: object | None = None
_SESSION_GRAPH_ONLY_RETRIEVER: object | None = None


@pytest.fixture(scope="session", autouse=True)
def _warm_backend_main_for_tests() -> None:
    """Import ``backend.main`` once per session (expensive router / schema wiring)."""
    global _SESSION_APP, _SESSION_GRAPH_ONLY_RETRIEVER
    from backend.main import app
    from backend.rag.hybrid_retriever import HybridRetriever

    _SESSION_APP = app
    _SESSION_GRAPH_ONLY_RETRIEVER = HybridRetriever(vector_store=None)


@pytest.fixture(autouse=True)
def _bind_graph_only_hybrid_retriever() -> Iterator[None]:
    """Avoid ChromaDB init when HTTP QA routes resolve HybridRetriever without app lifespan.

    Function-scoped rebind is required: some tests call ``reset_hybrid_retriever()``;
    a session-only bind would leave later tests falling through to
    ``create_hybrid_retriever()`` → real VectorStore (forbidden in tests).
    """
    from backend.rag.hybrid_retriever import bind_hybrid_retriever, reset_hybrid_retriever

    assert _SESSION_APP is not None and _SESSION_GRAPH_ONLY_RETRIEVER is not None
    app = _SESSION_APP
    retriever = _SESSION_GRAPH_ONLY_RETRIEVER
    prior = getattr(app.state, "hybrid_retriever", None)
    app.state.hybrid_retriever = retriever
    bind_hybrid_retriever(retriever)
    yield
    reset_hybrid_retriever()
    if prior is not None:
        app.state.hybrid_retriever = prior
    elif hasattr(app.state, "hybrid_retriever"):
        delattr(app.state, "hybrid_retriever")


@pytest.fixture(autouse=True)
def _disable_two_phase_extraction_for_legacy_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default tests to the single-phase extraction path to preserve existing mocks.

    New tests for the two-phase sub-graph should explicitly re-enable it with
    ``monkeypatch.setenv('EXTRACT_TWO_PHASE_ENABLED', 'true')``.
    """
    monkeypatch.setenv("EXTRACT_TWO_PHASE_ENABLED", "false")
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _attach_paper_service_compat_shims(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """D8: mount legacy ``_papers`` / ``_status`` shims on test ``PaperService`` instances only."""
    from backend.services.paper_service import PaperService

    from tests.helpers.compat_shims import attach_paper_service_compat_shims

    original_init = PaperService.__init__

    def _init_with_compat_shims(self, *args, **kwargs) -> None:
        original_init(self, *args, **kwargs)
        attach_paper_service_compat_shims(self)

    monkeypatch.setattr(PaperService, "__init__", _init_with_compat_shims)
    yield


@pytest.fixture(autouse=True)
def _ensure_demo_fixture_corpus(request: pytest.FixtureRequest) -> Iterator[None]:
    """Idempotent demo corpus seed (cheap when rows already exist).

    Kept function-scoped: session-only seeding via ``run_async`` can miss the
    pytest-asyncio loop affinity, and ``persistence_env`` remaps the DB URL.
    """
    if "persistence_env" in request.fixturenames:
        yield
        return

    from backend.repositories.async_bridge import run_async

    from tests.helpers.persistence_testkit import ensure_demo_fixture_corpus

    run_async(ensure_demo_fixture_corpus())
    yield


@pytest.fixture
def minimal_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "minimal.pdf"
    path.write_bytes(b"%PDF-1.4\n% minimal test pdf")
    return path


@contextmanager
def mock_pipeline_node_services(
    paper_id: str,
) -> Iterator[dict[str, MagicMock]]:
    """Patch workflow node services with successful mocks for a given paper_id."""
    from backend.agents.classifier_types import ClassifyResult
    from backend.agents.extract_types import ExtractResult
    from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
    from backend.schemas.paradigm import Paradigm, ParadigmClassification
    from backend.services.graph_persistence_service import GraphPersistenceService
    from backend.services.pipeline_completion_service import PipelineCompletionService

    classification = ParadigmClassification(
        paradigm=Paradigm.HSS,
        confidence=0.9,
        reason="mock",
    )
    graph = UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="N", type="Thesis")],
        edges=[
            GraphEdge(
                id="e1",
                source="n1",
                target="n1",
                label="REF",
                type="REF",
            ),
        ],
    )
    extract_result = ExtractResult(graph=graph, warnings=[])

    ingest_svc = MagicMock()
    ingest_svc.ingest = AsyncMock(
        return_value={
            "paper_id": paper_id,
            "full_text": "full-text",
            "classifier_input": "classifier-input",
        },
    )

    agent_svc = MagicMock()
    agent_svc.classify_paradigm = AsyncMock(return_value=ClassifyResult(classification=classification, warnings=[]))
    agent_svc.extract_graph = AsyncMock(return_value=extract_result)
    agent_svc.extract_graph_background = AsyncMock(return_value=extract_result)
    agent_svc.should_extract_in_background = MagicMock(return_value=False)

    persistence = GraphPersistenceService()
    completion_svc = PipelineCompletionService(graph_persistence=persistence)
    store_save = MagicMock(wraps=persistence._store.save)
    persistence._store.save = store_save  # type: ignore[method-assign]

    with (
        patch("backend.graph.nodes.get_ingest_service", return_value=ingest_svc),
        patch("backend.graph.nodes.get_agent_service", return_value=agent_svc),
        patch("backend.services.agent_service.get_agent_service", return_value=agent_svc),
        patch(
            "backend.graph.nodes.get_pipeline_completion_service",
            return_value=completion_svc,
        ),
        patch(
            "backend.services.rag_index_service.RagIndexService.index_paper_for_rag_async",
            new_callable=AsyncMock,
        ) as mock_rag_index,
        patch("backend.graph.nodes.ensure_head_refine_scheduled"),
        patch(
            "backend.graph.nodes.wait_for_refined_classifier_input",
            new=AsyncMock(side_effect=lambda _pid, _path, fallback, **_: (fallback, [])),
        ),
    ):
        mock_rag_index.return_value = None
        yield {
            "ingest": ingest_svc,
            "agent": agent_svc,
            "completion": completion_svc,
            "rag_index": mock_rag_index,
            "store_save": store_save,
        }


@pytest.fixture
def mock_pipeline_services():
    """Pytest fixture wrapper: use as `with mock_pipeline_services("paper-id"):` via request."""

    @contextmanager
    def _apply(paper_id: str) -> Iterator[dict[str, MagicMock]]:
        with mock_pipeline_node_services(paper_id) as mocks:
            yield mocks

    return _apply


@contextmanager
def mock_agent_services_only(
    paper_id: str,
) -> Iterator[dict[str, MagicMock]]:
    """Patch agent + store only; ingest runs real ``IngestService`` (BE-1 + platform)."""
    from backend.agents.classifier_types import ClassifyResult
    from backend.agents.extract_types import ExtractResult
    from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
    from backend.schemas.paradigm import Paradigm, ParadigmClassification
    from backend.services.graph_persistence_service import GraphPersistenceService
    from backend.services.pipeline_completion_service import PipelineCompletionService

    classification = ParadigmClassification(
        paradigm=Paradigm.STEM,
        confidence=0.91,
        reason="three-branch mock classify",
    )
    graph = UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.STEM,
        nodes=[GraphNode(id="n1", label="N", type="Method")],
        edges=[
            GraphEdge(
                id="e1",
                source="n1",
                target="n1",
                label="SUPPORTS",
                type="SUPPORTS",
                rationale="Mock self-supporting edge to satisfy quality gate coverage.",
                source_span="Mock textual anchor.",
                confidence="HIGH",
            ),
        ],
    )
    extract_result = ExtractResult(graph=graph, warnings=[])

    agent_svc = MagicMock()
    agent_svc.classify_paradigm = AsyncMock(return_value=ClassifyResult(classification=classification, warnings=[]))
    agent_svc.extract_graph = AsyncMock(return_value=extract_result)
    agent_svc.extract_graph_background = AsyncMock(return_value=extract_result)
    agent_svc.should_extract_in_background = MagicMock(return_value=False)

    with patch("backend.services.graph_persistence_service.GraphStore") as store_cls:
        store_cls.return_value.save = MagicMock()
        persistence = GraphPersistenceService(store=store_cls.return_value)
        completion_svc = PipelineCompletionService(graph_persistence=persistence)

        with (
            patch("backend.graph.nodes.get_agent_service", return_value=agent_svc),
            patch("backend.services.agent_service.get_agent_service", return_value=agent_svc),
            patch(
                "backend.graph.nodes.get_pipeline_completion_service",
                return_value=completion_svc,
            ),
            patch("backend.graph.nodes.ensure_head_refine_scheduled"),
            patch(
                "backend.graph.nodes.wait_for_refined_classifier_input",
                new=AsyncMock(side_effect=lambda _pid, _path, fallback, **_: (fallback, [])),
            ),
        ):
            yield {
                "agent": agent_svc,
                "completion": completion_svc,
                "store_save": store_cls.return_value.save,
            }


@pytest.fixture
def persistence_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolated SQLite DB + upload/graph dirs for persistence-core tests."""
    from backend.repositories.async_bridge import run_async

    db_path = tmp_path / "scholargraph.db"
    upload_dir = tmp_path / "uploads"
    graph_dir = tmp_path / "graphs"
    upload_dir.mkdir(parents=True, exist_ok=True)
    graph_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("UPLOAD_DIR", str(upload_dir))
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_dir))
    monkeypatch.setenv("SEED_DEMO_PAPERS", "false")
    reset_persistence_singletons()
    # Use the async bridge — pytest-asyncio may already have a running loop.
    run_async(init_isolated_database(db_path))
    yield {
        "db_path": db_path,
        "upload_dir": upload_dir,
        "graph_dir": graph_dir,
    }
    reset_persistence_singletons()


@pytest.fixture(autouse=True)
async def _cleanup_event_bus_worker_after_test() -> AsyncIterator[None]:
    """D17: await EventBus worker cancel so pytest does not leak pending tasks."""
    yield
    from backend.events.bus import astop_event_bus_worker

    await astop_event_bus_worker()


@pytest.fixture(autouse=True)
def _patrol_service_global_mock_vector_store(monkeypatch) -> None:
    """Avoid real ChromaDB in any test that calls get_patrol_service()."""
    from unittest.mock import AsyncMock

    from backend.services import patrol_service as ps_module

    def _mock_vector_store(*_args, **_kwargs):
        mock = AsyncMock()
        mock.query_chunks.return_value = []
        return mock

    def _mock_get_patrol_service():
        return ps_module.PatrolService(vector_store=_mock_vector_store())

    monkeypatch.setattr(ps_module, "get_patrol_service", _mock_get_patrol_service)
    if hasattr(ps_module.get_patrol_service, "cache_clear"):
        ps_module.get_patrol_service.cache_clear()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Stop background workers so pytest can exit without hanging on non-daemon threads."""
    try:
        from backend.rag.wipe_vector_sweep import reset_wipe_sweep_tasks_for_tests, stop_vector_cleanup_poller

        stop_vector_cleanup_poller()
        reset_wipe_sweep_tasks_for_tests()
    except Exception:
        pass
    try:
        from backend.pipeline.processing_watchdog import stop_processing_watchdog
        from backend.rag.indexing_watchdog import stop_indexing_watchdog

        stop_processing_watchdog(join_timeout_seconds=1.0)
        stop_indexing_watchdog(join_timeout_seconds=1.0)
    except Exception:
        pass
    from backend.events.bus import stop_all_event_bus_workers

    stop_all_event_bus_workers()
