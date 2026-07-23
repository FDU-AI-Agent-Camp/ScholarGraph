# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Decoupled unit tests for first-class delete / re-extract use-case services.

These tests exercise ``PaperDeleteService`` / ``ReextractService`` directly via
constructor DI — no ``PaperService`` facade, no real SQLite. Mocked repositories
prove domain exceptions surface cleanly on missing-row / active-pipeline branches.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from backend.api.exceptions import ApiError
from backend.schemas.paper import PaperStatus
from backend.services.paper_delete_service import PaperDeleteService
from backend.services.paper_pipeline_ops import PaperPipelineOpsService
from backend.services.reextract_service import ReextractService


def _mock_paper_repo(**overrides: object) -> AsyncMock:
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=None)
    repo.get_pdf_path = AsyncMock(return_value=None)
    repo.delete = AsyncMock(return_value=False)
    repo.reset_for_reextract = AsyncMock()
    for name, value in overrides.items():
        setattr(repo, name, value)
    return repo


def _mock_pipeline_ops() -> MagicMock:
    ops = MagicMock(spec=PaperPipelineOpsService)
    ops.clear_ephemeral_pipeline_state = AsyncMock()
    ops.reset_pipeline_for_reextract = AsyncMock()
    return ops


def test_delete_service_accepts_injected_repository_and_pipeline_ops() -> None:
    paper_repo = _mock_paper_repo()
    pipeline_ops = _mock_pipeline_ops()

    service = PaperDeleteService(paper_repo=paper_repo, pipeline_ops=pipeline_ops)

    assert service._paper_repository is paper_repo
    assert service._pipeline_ops is pipeline_ops


def test_reextract_service_accepts_injected_repository_and_pipeline_ops() -> None:
    paper_repo = _mock_paper_repo()
    pipeline_ops = _mock_pipeline_ops()

    service = ReextractService(paper_repo=paper_repo, pipeline_ops=pipeline_ops)

    assert service._paper_repository is paper_repo
    assert service._pipeline_ops is pipeline_ops


@pytest.mark.asyncio
async def test_delete_raises_domain_404_when_repository_returns_none() -> None:
    paper_repo = _mock_paper_repo(get=AsyncMock(return_value=None))
    pipeline_ops = _mock_pipeline_ops()
    service = PaperDeleteService(paper_repo=paper_repo, pipeline_ops=pipeline_ops)

    with pytest.raises(ApiError) as exc_info:
        await service.delete("missing-paper")

    err = exc_info.value
    assert err.code == "PAPER_NOT_FOUND"
    assert err.status_code == 404
    paper_repo.get.assert_awaited_once_with("missing-paper")
    pipeline_ops.clear_ephemeral_pipeline_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_reextract_raises_domain_404_when_repository_returns_none() -> None:
    paper_repo = _mock_paper_repo(get=AsyncMock(return_value=None))
    pipeline_ops = _mock_pipeline_ops()
    service = ReextractService(paper_repo=paper_repo, pipeline_ops=pipeline_ops)

    with pytest.raises(ApiError) as exc_info:
        await service.force_reextract("missing-paper")

    err = exc_info.value
    assert err.code == "PAPER_NOT_FOUND"
    assert err.status_code == 404
    paper_repo.get.assert_awaited_once_with("missing-paper")
    pipeline_ops.reset_pipeline_for_reextract.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_raises_409_for_processing_without_force() -> None:
    paper_repo = _mock_paper_repo(
        get=AsyncMock(return_value=SimpleNamespace(status=PaperStatus.PROCESSING)),
    )
    pipeline_ops = _mock_pipeline_ops()
    service = PaperDeleteService(paper_repo=paper_repo, pipeline_ops=pipeline_ops)

    with pytest.raises(ApiError) as exc_info:
        await service.delete("busy-paper", force=False)

    err = exc_info.value
    assert err.code == "PAPER_ALREADY_PROCESSING"
    assert err.status_code == 409
    paper_repo.delete.assert_not_awaited()
    pipeline_ops.clear_ephemeral_pipeline_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_reextract_raises_409_for_indexing_without_force() -> None:
    paper_repo = _mock_paper_repo(
        get=AsyncMock(return_value=SimpleNamespace(status=PaperStatus.INDEXING)),
    )
    pipeline_ops = _mock_pipeline_ops()
    service = ReextractService(paper_repo=paper_repo, pipeline_ops=pipeline_ops)

    with pytest.raises(ApiError) as exc_info:
        await service.force_reextract("indexing-paper", force=False)

    err = exc_info.value
    assert err.code == "PAPER_ALREADY_PROCESSING"
    assert err.status_code == 409
    paper_repo.reset_for_reextract.assert_not_awaited()
    pipeline_ops.reset_pipeline_for_reextract.assert_not_awaited()
