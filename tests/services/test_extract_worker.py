# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Tests for the background full-extraction worker (Slice 2)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.errors import ServiceError
from backend.services.extract_worker import (
    areset_extract_worker,
    get_full_extraction_task,
    reset_extract_worker,
    schedule_full_extraction,
)
from backend.services.paper_service import get_paper_service


def _register_paper(paper_id: str) -> None:
    from backend.schemas.paper import PaperDetail

    service = get_paper_service()
    now = datetime.now(UTC)
    service._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="bg test",
        status=PaperStatus.PROCESSING,
        created_at=now,
        updated_at=now,
    )
    service._status[paper_id] = PaperStatusData(
        paper_id=paper_id,
        status=PaperStatus.PROCESSING,
        percent=80,
        stage=PipelineStage.EXTRACTING,
        message="extracting",
        updated_at=now,
    )


@pytest.fixture(autouse=True)
async def _fresh_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "mock")
    from backend.config import Settings, get_settings
    from backend.services.paper_service import get_paper_service

    get_settings.cache_clear()
    get_paper_service.cache_clear()
    await areset_extract_worker()
    # Zero retry delay keeps mock-mode worker tests fast.
    _fast_settings = Settings(_env_file=None, llm_mode="mock", extract_chunk_retry_delay_s=0.0)
    monkeypatch.setattr("backend.services.extract_worker.get_settings", lambda: _fast_settings)
    yield
    await areset_extract_worker()
    get_paper_service.cache_clear()


class TestScheduleFullExtraction:
    async def test_schedules_background_task(self) -> None:
        paper_id = "bg-001"
        _register_paper(paper_id)
        classification = ParadigmClassification(
            paradigm=Paradigm.HSS,
            confidence=0.9,
            reason="test",
        )

        task = schedule_full_extraction(
            paper_id,
            "short text",
            Paradigm.HSS,
            classification,
        )

        assert task is get_full_extraction_task(paper_id)
        assert not task.done()
        await areset_extract_worker()

    async def test_idempotent_scheduling(self) -> None:
        paper_id = "bg-002"
        _register_paper(paper_id)
        classification = ParadigmClassification(paradigm=Paradigm.HSS, confidence=0.9, reason="test")

        task1 = schedule_full_extraction(paper_id, "text", Paradigm.HSS, classification)
        task2 = schedule_full_extraction(paper_id, "text", Paradigm.HSS, classification)

        assert task1 is task2
        await areset_extract_worker()

    async def test_background_task_finalizes_pipeline(self) -> None:
        from unittest.mock import AsyncMock, patch

        from tests.helpers.event_bus_testkit import drain_event_bus

        paper_id = "bg-003"
        _register_paper(paper_id)
        classification = ParadigmClassification(paradigm=Paradigm.HSS, confidence=0.9, reason="test")

        with patch(
            "backend.services.rag_index_service.RagIndexService.index_paper_for_rag_async",
            new_callable=AsyncMock,
            return_value=True,
        ):
            schedule_full_extraction(paper_id, "text", Paradigm.HSS, classification)
            # Wait for the mock-mode background task to complete.
            for _ in range(100):
                task = get_full_extraction_task(paper_id)
                if task is None or task.done():
                    break
                await asyncio.sleep(0.01)
            await drain_event_bus()

        status = await get_paper_service().get_status(paper_id)
        assert status.status == PaperStatus.READY

    async def test_background_task_marks_failed_on_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        paper_id = "bg-004"
        _register_paper(paper_id)
        classification = ParadigmClassification(paradigm=Paradigm.HSS, confidence=0.9, reason="test")

        async def _boom(*_args, **_kwargs):
            raise RuntimeError("chunked extraction failed")

        monkeypatch.setattr("backend.services.extract_worker._extract_chunked_two_phase", _boom)

        schedule_full_extraction(paper_id, "text", Paradigm.HSS, classification)
        for _ in range(100):
            task = get_full_extraction_task(paper_id)
            if task is None or task.done():
                break
            await asyncio.sleep(0.01)

        status = await get_paper_service().get_status(paper_id)
        assert status.status == PaperStatus.FAILED

    async def test_service_error_uses_custom_error_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        paper_id = "bg-005"
        _register_paper(paper_id)
        classification = ParadigmClassification(paradigm=Paradigm.HSS, confidence=0.9, reason="test")

        async def _service_error(*_args, **_kwargs):
            raise ServiceError(code="RATE_LIMIT_EXCEEDED", message="cloud throttled")

        monkeypatch.setattr("backend.services.extract_worker._extract_chunked_two_phase", _service_error)

        schedule_full_extraction(paper_id, "text", Paradigm.HSS, classification)
        for _ in range(100):
            task = get_full_extraction_task(paper_id)
            if task is None or task.done():
                break
            await asyncio.sleep(0.01)

        status = await get_paper_service().get_status(paper_id)
        assert status.status == PaperStatus.FAILED
        assert status.error_code == "RATE_LIMIT_EXCEEDED"
        assert status.failed_during == PipelineStage.EXTRACTING

    async def test_missing_paper_does_not_hang_worker(self) -> None:
        paper_id = "bg-missing-001"
        classification = ParadigmClassification(paradigm=Paradigm.HSS, confidence=0.9, reason="test")

        task = schedule_full_extraction(paper_id, "text", Paradigm.HSS, classification)
        for _ in range(100):
            if task.done():
                break
            await asyncio.sleep(0.01)

        assert task.done()
        assert get_full_extraction_task(paper_id) is None

    async def test_done_task_is_not_reused(self) -> None:
        paper_id = "bg-006"
        _register_paper(paper_id)
        classification = ParadigmClassification(paradigm=Paradigm.HSS, confidence=0.9, reason="test")

        task1 = schedule_full_extraction(paper_id, "text", Paradigm.HSS, classification)
        for _ in range(500):
            if task1.done():
                break
            await asyncio.sleep(0.02)

        task2 = schedule_full_extraction(paper_id, "text", Paradigm.HSS, classification)
        assert task1 is not task2
        assert not task2.done()

    async def test_reset_extract_worker_clears_active_task(self) -> None:
        paper_id = "bg-007"
        _register_paper(paper_id)
        classification = ParadigmClassification(paradigm=Paradigm.HSS, confidence=0.9, reason="test")

        schedule_full_extraction(paper_id, "text", Paradigm.HSS, classification)
        assert get_full_extraction_task(paper_id) is not None

        reset_extract_worker()
        assert get_full_extraction_task(paper_id) is None
