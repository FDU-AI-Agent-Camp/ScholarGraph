# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Tests for Phase-3 PaperServiceSyncAdapter (peripheral unidirectional bridge)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage
from backend.workflow.adapters.paper_service_sync import PaperServiceSyncAdapter


@pytest.fixture
def mock_paper_service() -> MagicMock:
    now = datetime.now(UTC)
    service = MagicMock()
    service.get_active_run_id = AsyncMock(return_value="run-1")
    service.set_active_run_id = AsyncMock()
    service.get_status = AsyncMock(
        return_value=PaperStatusData(
            paper_id="p1",
            status=PaperStatus.READY,
            percent=100,
            stage=None,
            message="ok",
            updated_at=now,
        )
    )
    service.fail_pipeline = AsyncMock(return_value=None)
    service.get_pipeline_graph_version = AsyncMock(return_value="3")
    return service


def test_sync_adapter_get_active_run_id_bridges(mock_paper_service: MagicMock) -> None:
    adapter = PaperServiceSyncAdapter(mock_paper_service)
    assert adapter.get_active_run_id("p1") == "run-1"
    mock_paper_service.get_active_run_id.assert_awaited_once_with("p1")


def test_sync_adapter_set_active_run_id_bridges(mock_paper_service: MagicMock) -> None:
    adapter = PaperServiceSyncAdapter(mock_paper_service)
    adapter.set_active_run_id("p1", "run-2")
    mock_paper_service.set_active_run_id.assert_awaited_once_with("p1", "run-2")


def test_sync_adapter_fail_pipeline_bridges(mock_paper_service: MagicMock) -> None:
    adapter = PaperServiceSyncAdapter(mock_paper_service)
    adapter.fail_pipeline(
        "p1",
        message="boom",
        error_code="PIPELINE_FAILED",
        failed_during=PipelineStage.EXTRACTING,
    )
    mock_paper_service.fail_pipeline.assert_awaited_once()


def test_sync_adapter_get_pipeline_graph_version_bridges(mock_paper_service: MagicMock) -> None:
    adapter = PaperServiceSyncAdapter(mock_paper_service)
    assert adapter.get_pipeline_graph_version("p1") == "3"
