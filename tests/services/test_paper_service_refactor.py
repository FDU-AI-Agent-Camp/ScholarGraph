# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Minimal smoke tests for PaperService facade decomposition (step 1)."""

from __future__ import annotations

from pathlib import Path

import pytest
from backend.graph.head_store import HeadStore
from backend.schemas.graph import GraphNode, UnifiedPaperGraph
from backend.schemas.ingest_head import IngestHead
from backend.schemas.paper import PaperStatus
from backend.schemas.paradigm import Paradigm
from backend.services.paper_service import get_paper_service
from backend.services.paper_warning_service import WarningType, get_paper_warning_service
from tests.helpers.persistence_testkit import register_test_paper


@pytest.fixture(autouse=True)
def _fresh_service() -> None:
    get_paper_service.cache_clear()
    yield
    get_paper_service.cache_clear()


@pytest.mark.asyncio
async def test_warning_service_shim_records_and_reads_extract_warnings() -> None:
    service = get_paper_service()
    paper_id = "refactor-warning-001"
    await register_test_paper(paper_id, status=PaperStatus.PROCESSING)

    await get_paper_warning_service().record(paper_id, WarningType.EXTRACT, ["extract_heuristic_fallback"])

    assert await get_paper_warning_service().get(paper_id, WarningType.EXTRACT) == ["extract_heuristic_fallback"]
    assert await service._warnings.get(paper_id, WarningType.EXTRACT) == ["extract_heuristic_fallback"]


@pytest.mark.asyncio
async def test_preview_facade_shim_persists_and_detects_availability() -> None:
    service = get_paper_service()
    paper_id = "refactor-preview-001"
    await register_test_paper(paper_id, status=PaperStatus.PROCESSING)
    graph = UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="Thesis", type="Thesis")],
        edges=[],
    )

    await service.save_preview_graph(paper_id, graph)
    await service.mark_preview_available(paper_id)

    assert await service.get_preview_graph(paper_id) == graph
    assert await service.is_preview_available(paper_id) is True


@pytest.mark.asyncio
async def test_head_refine_coordinator_shim_persists_to_disk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_DATA_DIR", str(tmp_path))
    from backend.config import get_settings

    get_settings.cache_clear()
    get_paper_service.cache_clear()

    service = get_paper_service()
    paper_id = "refactor-head-001"
    await register_test_paper(paper_id, status=PaperStatus.PENDING)
    merged = IngestHead(
        title="Refined Title",
        abstract="Refined abstract",
        sources={"title": "mineru", "abstract": "pymupdf"},
    )

    service.apply_head_refine(
        paper_id,
        merged=merged,
        classifier_input="Title: Refined Title",
        warnings=["mineru_unavailable"],
    )

    record = HeadStore(base_dir=tmp_path).load(paper_id)
    assert record is not None
    assert record.merged.title == "Refined Title"
    assert await get_paper_warning_service().get(paper_id, WarningType.HEAD_REFINE) == ["mineru_unavailable"]
    assert service.get_refined_classifier_input(paper_id) == "Title: Refined Title"

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_pipeline_ops_composed_via_facade_delegates_generation_guard() -> None:
    service = get_paper_service()
    paper_id = "refactor-pipeline-ops-001"
    await register_test_paper(paper_id, status=PaperStatus.PROCESSING)

    await service.begin_pipeline_generation(paper_id)
    token = await service.get_pipeline_generation_id(paper_id)

    assert token is not None
    assert await service._pipeline_ops.get_pipeline_generation_id(paper_id) == token


@pytest.mark.asyncio
async def test_detail_assembler_enriches_paper_detail() -> None:
    service = get_paper_service()
    paper_id = "refactor-assembler-001"
    await register_test_paper(paper_id, status=PaperStatus.PROCESSING)
    await get_paper_warning_service().record(paper_id, WarningType.EXTRACT, ["extract_heuristic_fallback"])
    await service.mark_preview_available(paper_id)

    paper = await service.get_paper(paper_id)

    assert paper.extract_warnings == ["extract_heuristic_fallback"]
    assert paper.preview_available is True
