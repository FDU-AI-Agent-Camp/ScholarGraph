# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Additional red-light tests (RED-05~10)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.red


@pytest.mark.red
def test_red_dual_write_validation_mode_not_implemented() -> None:
    from backend.services import paper_service

    assert not hasattr(paper_service.PaperService, "enable_dual_write_validation")


@pytest.mark.red
def test_red_mysql_driver_optional_extra_not_ci_gated() -> None:
    import importlib.util

    assert importlib.util.find_spec("pymysql") is None


@pytest.mark.red
@pytest.mark.asyncio
async def test_red_concurrent_pipeline_writes_without_database_locked(persistence_env) -> None:
    """Stress: parallel status UPSERT should not raise database is locked (P1.5)."""
    import asyncio
    from datetime import UTC, datetime

    from backend.repositories.paper_repository import PaperRepository
    from backend.repositories.pipeline_repository import PipelineRepository
    from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage

    paper_repo = PaperRepository()
    pipeline_repo = PipelineRepository()
    paper_id = "stress-001"
    await paper_repo.create(paper_id, "Stress", "/tmp/s.pdf")
    now = datetime.now(UTC)

    async def write_once(stage: PipelineStage, percent: int) -> None:
        await pipeline_repo.save_status(
            paper_id,
            PaperStatusData(
                paper_id=paper_id,
                status=PaperStatus.PROCESSING,
                percent=percent,
                stage=stage,
                message=stage.value,
                updated_at=now,
            ),
        )

    await asyncio.gather(
        write_once(PipelineStage.INGESTING, 20),
        write_once(PipelineStage.CLASSIFYING, 50),
        write_once(PipelineStage.EXTRACTING, 80),
    )


@pytest.mark.red
def test_red_pipeline_finalized_carries_page_break_offsets() -> None:
    from backend.events.types import PipelineFinalized

    fields = PipelineFinalized.__dataclass_fields__
    assert "page_break_offsets" in fields


@pytest.mark.red
def test_red_alembic_downgrade_to_base_supported(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.integration.test_alembic_migrations import run_alembic_cycle_assertions

    run_alembic_cycle_assertions(tmp_path, monkeypatch)


@pytest.mark.red
def test_red_persistence_metrics_exporter_not_implemented() -> None:
    import backend.services.paper_service as module

    assert not hasattr(module, "export_persistence_metrics")
