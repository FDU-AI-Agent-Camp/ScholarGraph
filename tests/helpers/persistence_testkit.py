"""Shared helpers for persistence-core tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from backend.db.base import get_async_engine, reset_database_caches
from backend.db.bootstrap import ensure_schema
from backend.repositories.paper_repository import get_paper_repository
from backend.repositories.pipeline_repository import get_pipeline_repository
from backend.schemas.paper import PaperStatus, PaperStatusData
from backend.services.paper_service import PaperService, get_paper_service, reset_persistence_singletons


async def init_isolated_database(db_path: Path) -> None:
    """Create schema in a dedicated SQLite file."""
    reset_database_caches()
    await ensure_schema(get_async_engine())


def run_async(coro: object) -> object:
    return asyncio.run(coro)  # type: ignore[arg-type]


async def register_test_paper(
    paper_id: str,
    *,
    title: str = "test paper",
    pdf_path: str | None = None,
    status: PaperStatus = PaperStatus.PENDING,
    with_status_row: bool = True,
) -> None:
    """Insert a paper row (+ optional pending pipeline snapshot) for service tests."""
    repo = get_paper_repository()
    resolved_pdf = pdf_path or f"./uploads/{paper_id}.pdf"
    existing = await repo.get(paper_id)
    if existing is None:
        await repo.create(paper_id, title, resolved_pdf, status=status)
    if with_status_row:
        now = datetime.now(UTC)
        await get_pipeline_repository().save_status(
            paper_id,
            PaperStatusData(
                paper_id=paper_id,
                status=status,
                percent=0 if status == PaperStatus.PENDING else 20,
                stage=None if status == PaperStatus.PENDING else None,
                message="test fixture",
                updated_at=now,
            ),
        )


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
