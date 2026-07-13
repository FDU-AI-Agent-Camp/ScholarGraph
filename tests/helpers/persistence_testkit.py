"""Shared helpers for persistence-core tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

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


async def ensure_demo_fixture_corpus() -> None:
    """Upsert OpenAPI demo papers/status/graph paths when core fixture rows are absent."""
    from backend.services.paper_fixture_seed import refresh_demo_status_snapshots, seed_from_fixtures

    await ensure_schema(get_async_engine())
    paper_repo = get_paper_repository()
    core_demo_ids = ("stem-001", "hss-001", "hss-002", "hss-failed-001")
    corpus_complete = True
    for paper_id in core_demo_ids:
        if await paper_repo.get(paper_id) is None:
            corpus_complete = False
            break
    if corpus_complete:
        await paper_repo.bump_list_rank(core_demo_ids)
        await refresh_demo_status_snapshots(core_demo_ids)
        return
    await seed_from_fixtures(paper_repo, get_pipeline_repository())
    await paper_repo.bump_list_rank(core_demo_ids)
    await refresh_demo_status_snapshots(core_demo_ids)


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


def simulate_service_crash() -> None:
    """Drop the in-process ``PaperService`` singleton without DB cleanup (D6 crash-recovery)."""
    get_paper_service.cache_clear()


async def wipe_all_paper_rows() -> None:
    """Delete all paper and pipeline rows while keeping schema and singletons."""
    from backend.db.base import get_async_session_factory
    from backend.db.models import PaperRow, PipelineRunRow
    from sqlalchemy import delete

    async with get_async_session_factory()() as session:
        await session.execute(delete(PipelineRunRow))
        await session.execute(delete(PaperRow))
        await session.commit()


def expected_demo_fixture_count() -> int:
    """Number of demo papers declared in ``docs/api/fixtures/papers-list.json``."""
    import json

    from backend.services.paper_fixture_seed import FIXTURES_DIR

    list_path = FIXTURES_DIR / "papers-list.json"
    payload = json.loads(list_path.read_text(encoding="utf-8"))
    return len(payload["data"]["items"])


def mock_graph_persistence(
    paper_id: str,
    *,
    graph_dir: Path | str | None = None,
) -> MagicMock:
    """GraphPersistenceService mock whose ``save`` returns a concrete graph path (D7)."""
    from unittest.mock import MagicMock

    from backend.services.graph_persistence_service import GraphPersistenceService

    persistence = MagicMock(spec=GraphPersistenceService)
    if graph_dir is not None:
        graph_path = str(Path(graph_dir) / f"{paper_id}.json")
    else:
        graph_path = f"/mock/graphs/{paper_id}.json"
    persistence.save.return_value = graph_path
    return persistence
