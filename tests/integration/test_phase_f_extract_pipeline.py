# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Phase F integration: LLM extract + heuristic fallback through LangGraph pipeline."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE
from backend.agents.extract_types import ExtractResult
from backend.graph.workflow import run_paper_pipeline
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.schemas.paradigm import Paradigm
from backend.services.paper_service import get_paper_service
from backend.services.paper_warning_service import WarningType, get_paper_warning_service

from tests.conftest import mock_pipeline_node_services

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_pipeline_extract_fallback_still_reaches_ready(integration_paper: tuple[str, Path]) -> None:
    paper_id, pdf_path = integration_paper
    graph = UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="Thesis", type="Thesis")],
        edges=[],
    )

    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["agent"].extract_graph = AsyncMock(
            return_value=ExtractResult(
                graph=graph,
                warnings=[EXTRACT_HEURISTIC_FALLBACK_CODE],
            ),
        )
        final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("failed") is not True
    assert final.get("extract_warnings") == [EXTRACT_HEURISTIC_FALLBACK_CODE]

    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.READY
    assert status.extract_warnings == [EXTRACT_HEURISTIC_FALLBACK_CODE]


@pytest.mark.asyncio
async def test_pipeline_extract_success_has_no_extract_warnings(integration_paper: tuple[str, Path]) -> None:
    paper_id, pdf_path = integration_paper
    graph = UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[
            GraphNode(id="n1", label="Sub", type="SubArgument"),
            GraphNode(id="n2", label="Thesis", type="Thesis"),
        ],
        edges=[
            GraphEdge(
                id="e1",
                source="n1",
                target="n2",
                label="SUPPORTS",
                type="SUPPORTS",
                rationale="n1 supports n2",
            ),
        ],
    )

    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["agent"].extract_graph = AsyncMock(
            return_value=ExtractResult(graph=graph, warnings=[]),
        )
        final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("failed") is not True
    assert final.get("extract_warnings", []) == []

    status = await get_paper_service().get_status(paper_id)
    assert status.extract_warnings == []


@pytest.mark.asyncio
async def test_pipeline_extract_node_records_warnings_via_paper_service(
    integration_paper: tuple[str, Path],
) -> None:
    paper_id, pdf_path = integration_paper
    graph = UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.STEM,
        nodes=[GraphNode(id="n1", label="Method", type="Method")],
        edges=[],
    )

    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["agent"].extract_graph = AsyncMock(
            return_value=ExtractResult(
                graph=graph,
                warnings=[EXTRACT_HEURISTIC_FALLBACK_CODE],
            ),
        )
        warning_service = get_paper_warning_service()
        record_warnings = MagicMock(wraps=warning_service.record)
        with patch.object(warning_service, "record", record_warnings):
            await run_paper_pipeline(paper_id, pdf_path)

    record_warnings.assert_called_once_with(
        paper_id,
        WarningType.EXTRACT,
        [EXTRACT_HEURISTIC_FALLBACK_CODE],
    )


@pytest.mark.asyncio
async def test_pipeline_extract_failure_does_not_write_extract_warnings(
    integration_paper: tuple[str, Path],
) -> None:
    from backend.services.errors import ServiceError

    paper_id, pdf_path = integration_paper

    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["agent"].extract_graph = AsyncMock(
            side_effect=ServiceError("PIPELINE_FAILED", "extract failed hard"),
        )
        final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("failed") is True
    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.FAILED
    assert status.failed_during == PipelineStage.EXTRACTING
    assert status.extract_warnings == []
