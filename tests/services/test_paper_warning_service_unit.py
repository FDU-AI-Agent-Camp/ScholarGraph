# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Pure unit tests for PaperWarningService — mock PipelineRepository only.

Arrange cost target vs legacy PaperService + persistence_env path:
legacy ≈ fixture tree (persistence_env + registered_paper + get_paper_service)
         + 2–4 lines of act; this file ≈ 3–6 lines of AsyncMock wiring.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage
from backend.services.paper_warning_service import PaperWarningService, WarningType


def _snapshot(
    paper_id: str = "warn-unit-001",
    *,
    head_refine: list[str] | None = None,
    classify: list[str] | None = None,
    extract: list[str] | None = None,
) -> PaperStatusData:
    return PaperStatusData(
        paper_id=paper_id,
        status=PaperStatus.PROCESSING,
        percent=50,
        stage=PipelineStage.CLASSIFYING,
        message="unit",
        updated_at=datetime.now(UTC),
        head_refine_warnings=head_refine or [],
        classify_warnings=classify or [],
        extract_warnings=extract or [],
    )


def _repo() -> MagicMock:
    repo = MagicMock()
    repo.record_warnings = AsyncMock()
    repo.get_latest = AsyncMock(return_value=None)
    return repo


@pytest.mark.asyncio
async def test_record_empty_list_is_noop() -> None:
    repo = _repo()
    service = PaperWarningService(pipeline_repo=repo)

    await service.record("warn-unit-001", WarningType.HEAD_REFINE, [])

    repo.record_warnings.assert_not_awaited()


@pytest.mark.asyncio
async def test_record_routes_bucket_kwargs() -> None:
    repo = _repo()
    service = PaperWarningService(pipeline_repo=repo)

    await service.record("warn-unit-001", WarningType.EXTRACT, ["extract_heuristic_fallback"])

    repo.record_warnings.assert_awaited_once_with(
        "warn-unit-001",
        extract=["extract_heuristic_fallback"],
    )


@pytest.mark.asyncio
async def test_get_returns_empty_when_snapshot_missing() -> None:
    repo = _repo()
    service = PaperWarningService(pipeline_repo=repo)

    assert await service.get("missing", WarningType.CLASSIFY) == []


@pytest.mark.asyncio
async def test_get_reads_selected_bucket() -> None:
    repo = _repo()
    repo.get_latest = AsyncMock(
        return_value=_snapshot(
            head_refine=["mineru_unavailable"],
            classify=["classifier_heuristic_fallback"],
            extract=["extract_heuristic_fallback"],
        ),
    )
    service = PaperWarningService(pipeline_repo=repo)

    assert await service.get("warn-unit-001", WarningType.HEAD_REFINE) == ["mineru_unavailable"]
    assert await service.get("warn-unit-001", WarningType.CLASSIFY) == ["classifier_heuristic_fallback"]
    assert await service.get("warn-unit-001", WarningType.EXTRACT) == ["extract_heuristic_fallback"]


@pytest.mark.asyncio
async def test_get_extract_and_classify_single_read() -> None:
    repo = _repo()
    repo.get_latest = AsyncMock(
        return_value=_snapshot(
            classify=["classifier_heuristic_fallback"],
            extract=["extract_heuristic_fallback"],
        ),
    )
    service = PaperWarningService(pipeline_repo=repo)

    extract, classify = await service.get_extract_and_classify("warn-unit-001")

    assert extract == ["extract_heuristic_fallback"]
    assert classify == ["classifier_heuristic_fallback"]
    repo.get_latest.assert_awaited_once_with("warn-unit-001")
