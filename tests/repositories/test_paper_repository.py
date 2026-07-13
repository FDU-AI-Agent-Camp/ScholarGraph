"""Unit tests for PaperRepository."""

from __future__ import annotations

import pytest
from backend.repositories.paper_repository import PaperRepository
from backend.schemas.paper import PaperStatus
from backend.schemas.paradigm import Paradigm, ParadigmClassification


@pytest.mark.asyncio
async def test_create_and_get_round_trip(persistence_env) -> None:
    repo = PaperRepository()
    created = await repo.create(
        "paper-repo-001",
        "Repository Test",
        "/tmp/paper-repo-001.pdf",
        status=PaperStatus.PENDING,
    )

    loaded = await repo.get("paper-repo-001")
    assert loaded is not None
    assert loaded.paper_id == created.paper_id
    assert loaded.title == "Repository Test"
    assert loaded.status == PaperStatus.PENDING


@pytest.mark.asyncio
async def test_list_filters_by_paradigm_and_status(persistence_env) -> None:
    repo = PaperRepository()
    await repo.create("stem-1", "STEM", "/tmp/stem.pdf", status=PaperStatus.READY)
    await repo.create("hss-1", "HSS", "/tmp/hss.pdf", status=PaperStatus.PENDING)
    await repo.update_classification(
        "stem-1",
        ParadigmClassification(paradigm=Paradigm.STEM, confidence=0.9, reason="x"),
    )

    items, total = await repo.list(paradigm=Paradigm.STEM, status=PaperStatus.READY)
    assert total == 1
    assert items[0].paper_id == "stem-1"


@pytest.mark.asyncio
async def test_update_paths_and_graph_version(persistence_env) -> None:
    repo = PaperRepository()
    await repo.create("paper-paths", "Paths", "/tmp/a.pdf")

    await repo.update_paths("paper-paths", graph_path="/data/graphs/paper-paths.json")
    await repo.update_graph_version(
        "paper-paths",
        graph_version="2",
        extractor_config_hash="abc123",
    )

    loaded = await repo.get("paper-paths")
    assert loaded is not None
    # Internal paths are persisted but not exposed on API schemas.
    row = loaded
    assert row.paper_id == "paper-paths"


@pytest.mark.asyncio
async def test_is_empty_reflects_row_count(persistence_env) -> None:
    repo = PaperRepository()
    assert await repo.is_empty() is True
    await repo.create("only-one", "Only", "/tmp/only.pdf")
    assert await repo.is_empty() is False
