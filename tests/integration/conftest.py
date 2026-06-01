"""Shared fixtures for integration tests (pipeline + V1 DoD A-05～A-08)."""

from __future__ import annotations

import importlib.util
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from backend.config import get_settings
from backend.graph.store import GraphStore
from backend.llm.client import reset_llm_client_cache
from backend.main import app
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm
from backend.services.paper_service import get_paper_service
from httpx import ASGITransport, AsyncClient

from tests.conftest import RUN_PIPELINE_SCRIPT


def _load_run_pipeline_module():
    spec = importlib.util.spec_from_file_location("run_pipeline", RUN_PIPELINE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def integration_paper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, Path]:
    """Pending paper + minimal PDF registered for ``run_paper_pipeline`` tests."""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("UPLOAD_DIR", str(upload_dir))
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


@pytest.fixture
def mock_llm_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """LLM_MODE=mock + isolated graph dir; hss-001 graph on disk for qa_stream."""
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_dir))
    get_settings.cache_clear()
    reset_llm_client_cache()
    get_paper_service.cache_clear()

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
    yield graph_dir
    get_settings.cache_clear()
    reset_llm_client_cache()
    get_paper_service.cache_clear()


@pytest.fixture
async def api_client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
