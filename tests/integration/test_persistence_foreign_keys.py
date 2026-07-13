"""Integration test: foreign key cascade delete (INT-FK-01)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from backend.repositories.paper_repository import PaperRepository
from backend.repositories.pipeline_repository import PipelineRepository
from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_paper_cascades_pipeline_run(persistence_env) -> None:
    paper_repo = PaperRepository()
    pipeline_repo = PipelineRepository()
    await paper_repo.create("fk-001", "FK", "/tmp/fk.pdf")
    now = datetime.now(UTC)
    await pipeline_repo.save_status(
        "fk-001",
        PaperStatusData(
            paper_id="fk-001",
            status=PaperStatus.PROCESSING,
            percent=20,
            stage=PipelineStage.INGESTING,
            message="ingesting",
            updated_at=now,
        ),
    )
    assert await pipeline_repo.get_latest("fk-001") is not None

    assert await paper_repo.delete("fk-001") is True
    assert await pipeline_repo.get_latest("fk-001") is None
