"""Shared fixtures for integration tests (pipeline + V1 DoD A-05～A-08)."""

from __future__ import annotations

import asyncio
import importlib.util
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from backend.config import get_settings
from backend.graph.qa_samples import seed_m2_qa_graph
from backend.graph.store import GraphStore
from backend.llm.client import reset_llm_client_cache
from backend.main import app
from backend.repositories.paper_repository import get_paper_repository
from backend.repositories.pipeline_repository import get_pipeline_repository
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm
from backend.services.paper_fixture_seed import seed_from_fixtures
from backend.services.paper_service import get_paper_service
from httpx import ASGITransport, AsyncClient

from tests.conftest import RUN_PIPELINE_SCRIPT
from tests.helpers.persistence_testkit import (
    init_isolated_database,
    register_ready_paper,
    reset_persistence_singletons,
    run_async,
    setup_qa_persistence_env,
)


def _load_run_pipeline_module():
    spec = importlib.util.spec_from_file_location("run_pipeline", RUN_PIPELINE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def integration_paper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, Path]:
    """Pending paper + minimal PDF registered for ``run_paper_pipeline`` tests."""
    db_path = tmp_path / "scholargraph.db"
    upload_dir = tmp_path / "uploads"
    graph_dir = tmp_path / "graphs"
    upload_dir.mkdir(parents=True, exist_ok=True)
    graph_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("UPLOAD_DIR", str(upload_dir))
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_dir))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("SEED_DEMO_PAPERS", "false")
    reset_persistence_singletons()
    asyncio.run(init_isolated_database(db_path))
    get_settings.cache_clear()
    get_paper_service.cache_clear()

    pdf_path = tmp_path / "integration.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% integration pipeline test")

    paper_id = "integration-paper-001"
    run_pipeline = _load_run_pipeline_module()
    run_pdf = run_pipeline.register_paper_for_pipeline(
        paper_id,
        pdf_path,
        copy_to_upload_dir=False,
    )
    return paper_id, run_pdf


def _seed_openapi_demo_corpus() -> None:
    run_async(
        seed_from_fixtures(get_paper_repository(), get_pipeline_repository()),
    )


@pytest.fixture
def mock_llm_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """LLM_MODE=mock + isolated graph dir; hss-001 graph on disk and READY in DB."""
    graph_dir = tmp_path / "graphs"
    setup_qa_persistence_env(tmp_path, monkeypatch, graph_dir=graph_dir)
    _seed_openapi_demo_corpus()
    monkeypatch.setenv("LLM_MODE", "mock")
    get_settings.cache_clear()
    reset_llm_client_cache()

    GraphStore(base_dir=graph_dir).save(
        UnifiedPaperGraph(
            paper_id="hss-001",
            paradigm=Paradigm.HSS,
            nodes=[
                GraphNode(id="n1", label="核心论点", type="Thesis", data={}),
                GraphNode(id="n2", label="分论点", type="SubArgument", data={}),
                GraphNode(id="n_lens", label="历史制度主义", type="AnalyticalLens", data={}),
            ],
            edges=[
                GraphEdge(
                    id="e1",
                    source="n2",
                    target="n1",
                    label="SUB_ARGUMENT_OF",
                    type="SUB_ARGUMENT_OF",
                ),
            ],
        ),
    )
    run_async(register_ready_paper("hss-001"))
    yield graph_dir
    get_settings.cache_clear()
    reset_llm_client_cache()
    get_paper_service.cache_clear()


@pytest.fixture
def graph_hss_fixture_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Isolated GRAPH_DATA_DIR seeded with docs/api/fixtures/graph-hss.json (hss-001)."""
    graph_dir = tmp_path / "graphs"
    setup_qa_persistence_env(tmp_path, monkeypatch, graph_dir=graph_dir)
    _seed_openapi_demo_corpus()
    seed_m2_qa_graph(graph_dir)
    run_async(register_ready_paper("hss-001"))
    yield graph_dir
    get_settings.cache_clear()
    get_paper_service.cache_clear()


@pytest.fixture
def upload_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated upload directory for POST /papers integration tests."""
    upload_path = tmp_path / "uploads"
    upload_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("UPLOAD_DIR", str(upload_path))
    get_settings.cache_clear()
    get_paper_service.cache_clear()
    yield upload_path
    get_settings.cache_clear()
    get_paper_service.cache_clear()


@pytest.fixture
def mock_upload_pipeline_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    """Isolated upload + graph dirs and LLM_MODE=mock for POST /papers → pipeline tests."""
    upload_path = tmp_path / "uploads"
    graph_path = tmp_path / "graphs"
    upload_path.mkdir(parents=True, exist_ok=True)
    graph_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("UPLOAD_DIR", str(upload_path))
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_path))
    monkeypatch.setenv("LLM_MODE", "mock")
    get_settings.cache_clear()
    get_paper_service.cache_clear()
    yield upload_path, graph_path
    get_settings.cache_clear()
    get_paper_service.cache_clear()


@pytest.fixture
async def api_client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
