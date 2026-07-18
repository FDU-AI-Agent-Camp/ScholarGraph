# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Async persistence and dual-media ordering for HeadRefineCoordinator."""

from __future__ import annotations

from pathlib import Path

import pytest
from backend.graph.head_store import HeadStore
from backend.repositories.pipeline_repository import PipelineRepository
from backend.schemas.ingest_head import IngestHead
from backend.schemas.paper import PaperStatus
from backend.services.head_refine_coordinator import HeadRefineCoordinator
from backend.services.paper_core_service import PaperCoreService
from backend.services.paper_warning_service import PaperWarningService, WarningType
from tests.helpers.persistence_testkit import register_test_paper


@pytest.mark.asyncio
async def test_apply_async_persists_disk_and_warnings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_DATA_DIR", str(tmp_path))
    from backend.config import get_settings

    get_settings.cache_clear()

    coordinator = HeadRefineCoordinator(
        core_service=PaperCoreService(),
        warning_service=PaperWarningService(),
    )
    paper_id = "async-head-001"
    await register_test_paper(paper_id, status=PaperStatus.PENDING)
    merged = IngestHead(
        title="Async Title",
        abstract="Async abstract",
        sources={"title": "mineru", "abstract": "pymupdf"},
    )

    await coordinator.apply(
        paper_id,
        merged=merged,
        classifier_input="Title: Async Title",
        warnings=["mineru_unavailable"],
    )

    record = HeadStore(base_dir=tmp_path).load(paper_id)
    assert record is not None
    assert record.merged.title == "Async Title"
    warnings = await PipelineRepository().get_latest(paper_id)
    assert warnings is not None
    assert warnings.head_refine_warnings == ["mineru_unavailable"]

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_apply_is_idempotent_on_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_DATA_DIR", str(tmp_path))
    from backend.config import get_settings

    get_settings.cache_clear()

    warning_service = PaperWarningService()
    coordinator = HeadRefineCoordinator(
        core_service=PaperCoreService(),
        warning_service=warning_service,
    )
    paper_id = "async-head-retry-001"
    await register_test_paper(paper_id, status=PaperStatus.PENDING)
    merged = IngestHead(
        title="Retry Title",
        abstract="Retry abstract",
        sources={"title": "grobid", "abstract": "pymupdf"},
    )
    payload = {
        "merged": merged,
        "classifier_input": "Title: Retry Title",
        "warnings": ["grobid_unavailable"],
    }

    await coordinator.apply(paper_id, **payload)
    await coordinator.apply(paper_id, **payload)

    assert await warning_service.get(paper_id, WarningType.HEAD_REFINE) == ["grobid_unavailable"]
    record = HeadStore(base_dir=tmp_path).load(paper_id)
    assert record is not None
    assert record.merged.title == "Retry Title"

    get_settings.cache_clear()
