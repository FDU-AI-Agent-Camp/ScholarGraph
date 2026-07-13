"""Shared helpers for persistence-core tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from backend.config import get_settings
from backend.db.base import get_async_engine, reset_database_caches
from backend.db.bootstrap import ensure_schema
from backend.graph.store import GraphStore
from backend.repositories.async_bridge import run_async
from backend.repositories.paper_repository import get_paper_repository
from backend.repositories.pipeline_repository import get_pipeline_repository
from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage
from backend.services.paper_service import PaperService, get_paper_service, reset_persistence_singletons


async def init_isolated_database(db_path: Path) -> None:
    """Create schema in a dedicated SQLite file."""
    reset_database_caches()
    await ensure_schema(get_async_engine())


def _ready_pipeline_snapshot(paper_id: str, status: PaperStatus) -> PaperStatusData:
    now = datetime.now(UTC)
    if status in {PaperStatus.READY, PaperStatus.READY_WITH_WARNINGS}:
        return PaperStatusData(
            paper_id=paper_id,
            status=status,
            percent=100,
            stage=PipelineStage.READY,
            message="ready for QA tests",
            updated_at=now,
        )
    return PaperStatusData(
        paper_id=paper_id,
        status=status,
        percent=0 if status == PaperStatus.PENDING else 20,
        stage=None if status == PaperStatus.PENDING else None,
        message="test fixture",
        updated_at=now,
    )


async def register_test_paper(
    paper_id: str,
    *,
    title: str = "test paper",
    pdf_path: str | None = None,
    status: PaperStatus = PaperStatus.PENDING,
    with_status_row: bool = True,
) -> None:
    """Insert a paper row (+ optional pipeline snapshot) for service tests."""
    repo = get_paper_repository()
    resolved_pdf = pdf_path or f"./uploads/{paper_id}.pdf"
    existing = await repo.get(paper_id)
    if existing is None:
        await repo.create(paper_id, title, resolved_pdf, status=status)
    if with_status_row:
        await get_pipeline_repository().save_status(
            paper_id,
            _ready_pipeline_snapshot(paper_id, status),
        )


async def register_ready_paper(
    paper_id: str,
    *,
    title: str = "demo paper",
    pdf_path: str | None = None,
    status: PaperStatus = PaperStatus.READY,
) -> None:
    """Register a paper row with READY pipeline snapshot for QA / SSE tests."""
    await register_test_paper(
        paper_id,
        title=title,
        pdf_path=pdf_path,
        status=status,
        with_status_row=True,
    )


def setup_qa_persistence_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    graph_dir: Path | None = None,
    db_name: str = "scholargraph.db",
) -> dict[str, Path]:
    """Isolated SQLite + graph/upload dirs for QA tests that read PaperService from DB."""
    db_path = tmp_path / db_name
    resolved_graph = graph_dir or (tmp_path / "graphs")
    upload_dir = tmp_path / "uploads"
    resolved_graph.mkdir(parents=True, exist_ok=True)
    upload_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("UPLOAD_DIR", str(upload_dir))
    monkeypatch.setenv("GRAPH_DATA_DIR", str(resolved_graph))
    monkeypatch.setenv("SEED_DEMO_PAPERS", "false")
    reset_persistence_singletons()
    run_async(init_isolated_database(db_path))
    get_settings.cache_clear()
    get_paper_service.cache_clear()
    return {
        "db_path": db_path,
        "graph_dir": resolved_graph,
        "upload_dir": upload_dir,
    }


async def setup_qa_persistence_env_async(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    graph_dir: Path | None = None,
    db_name: str = "scholargraph.db",
) -> dict[str, Path]:
    """Async variant for pytest-asyncio fixtures (avoids nested event-loop bridges)."""
    db_path = tmp_path / db_name
    resolved_graph = graph_dir or (tmp_path / "graphs")
    upload_dir = tmp_path / "uploads"
    resolved_graph.mkdir(parents=True, exist_ok=True)
    upload_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("UPLOAD_DIR", str(upload_dir))
    monkeypatch.setenv("GRAPH_DATA_DIR", str(resolved_graph))
    monkeypatch.setenv("SEED_DEMO_PAPERS", "false")
    reset_persistence_singletons()
    await init_isolated_database(db_path)
    get_settings.cache_clear()
    get_paper_service.cache_clear()
    return {
        "db_path": db_path,
        "graph_dir": resolved_graph,
        "upload_dir": upload_dir,
    }


async def seed_qa_graph_with_db_async(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    graph: UnifiedPaperGraph,
    *,
    graph_dir: Path | None = None,
    status: PaperStatus = PaperStatus.READY,
) -> GraphStore:
    """Async variant of :func:`seed_qa_graph_with_db` for pytest-asyncio fixtures."""
    env = await setup_qa_persistence_env_async(tmp_path, monkeypatch, graph_dir=graph_dir)
    store = GraphStore(base_dir=env["graph_dir"])
    store.save(graph)
    await register_ready_paper(graph.paper_id, status=status)
    return store


def seed_qa_graph_with_db(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    graph: UnifiedPaperGraph,
    *,
    graph_dir: Path | None = None,
    status: PaperStatus = PaperStatus.READY,
) -> GraphStore:
    """Persist graph JSON and register the paper row for QA engine / HTTP routes."""
    env = setup_qa_persistence_env(tmp_path, monkeypatch, graph_dir=graph_dir)
    store = GraphStore(base_dir=env["graph_dir"])
    store.save(graph)
    run_async(register_ready_paper(graph.paper_id, status=status))
    return store


@pytest.fixture
def persistence_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolated SQLite DB + upload/graph dirs for persistence tests."""
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
    run_async(init_isolated_database(db_path))
    yield {
        "db_path": db_path,
        "upload_dir": upload_dir,
        "graph_dir": graph_dir,
    }
    reset_persistence_singletons()


async def restart_paper_service() -> PaperService:
    """Simulate process restart by clearing singleton caches."""
    reset_persistence_singletons()
    service = get_paper_service()
    await service.bootstrap()
    return service
