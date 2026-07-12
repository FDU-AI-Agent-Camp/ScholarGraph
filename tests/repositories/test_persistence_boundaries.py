"""Boundary tests for persistence repositories."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from backend.repositories.paper_repository import PaperRepository
from backend.repositories.pipeline_repository import PipelineRepository
from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage


@pytest.mark.asyncio
async def test_list_pagination_offset_and_limit(persistence_env) -> None:
    repo = PaperRepository()
    for index in range(5):
        await repo.create(f"page-{index}", f"Paper {index}", f"/tmp/{index}.pdf")

    page, total = await repo.list(offset=2, limit=2)
    assert total == 5
    assert len(page) == 2
    assert page[0].paper_id == "page-2"


@pytest.mark.asyncio
async def test_list_limit_zero_returns_empty_page(persistence_env) -> None:
    repo = PaperRepository()
    await repo.create("solo", "Solo", "/tmp/solo.pdf")
    page, total = await repo.list(limit=0)
    assert total == 1
    assert page == []


@pytest.mark.asyncio
async def test_get_missing_paper_returns_none(persistence_env) -> None:
    repo = PaperRepository()
    assert await repo.get("missing-uuid") is None


@pytest.mark.asyncio
async def test_pipeline_get_latest_without_row_returns_none(persistence_env) -> None:
    repo = PaperRepository()
    pipeline_repo = PipelineRepository()
    await repo.create("no-status", "No Status", "/tmp/no-status.pdf")
    assert await pipeline_repo.get_latest("no-status") is None


@pytest.mark.asyncio
async def test_record_warnings_noop_on_empty_lists(persistence_env) -> None:
    paper_repo = PaperRepository()
    pipeline_repo = PipelineRepository()
    await paper_repo.create("noop", "Noop", "/tmp/noop.pdf")
    now = datetime.now(UTC)
    await pipeline_repo.save_status(
        "noop",
        PaperStatusData(
            paper_id="noop",
            status=PaperStatus.PENDING,
            percent=0,
            stage=None,
            message="pending",
            updated_at=now,
        ),
    )
    await pipeline_repo.record_warnings("noop")
    latest = await pipeline_repo.get_latest("noop")
    assert latest is not None
    assert latest.classify_warnings == []


@pytest.mark.asyncio
async def test_save_status_rejects_unknown_paper_id(persistence_env) -> None:
    pipeline_repo = PipelineRepository()
    now = datetime.now(UTC)
    with pytest.raises(KeyError, match="paper not found"):
        await pipeline_repo.save_status(
            "ghost",
            PaperStatusData(
                paper_id="ghost",
                status=PaperStatus.PENDING,
                percent=0,
                stage=None,
                message="pending",
                updated_at=now,
            ),
        )


@pytest.mark.asyncio
async def test_title_boundary_accepts_long_title(persistence_env) -> None:
    repo = PaperRepository()
    long_title = "A" * 500
    created = await repo.create("long-title", long_title, "/tmp/long.pdf")
    assert created.title == long_title
