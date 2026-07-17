# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Tests for MVP skeleton preview extraction (Slice 1)."""

from __future__ import annotations

import pytest
from backend.agents.extractor import (
    MVP_SKELETON_PREVIEW_CODE,
    _build_mvp_input,
    _save_preview_graph,
    extract,
)
from backend.config import get_settings
from backend.schemas.graph import GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperDetail, PaperStatus, PaperStatusData, PipelineStage
from backend.schemas.paradigm import Paradigm
from backend.services.paper_service import get_paper_service


def _register_paper(paper_id: str, status: PaperStatus = PaperStatus.PROCESSING) -> None:
    """Register a paper in PaperService so preview saving can succeed."""
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    service = get_paper_service()
    service._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="preview test",
        status=status,
        created_at=now,
        updated_at=now,
    )
    service._status[paper_id] = PaperStatusData(
        paper_id=paper_id,
        status=status,
        percent=10,
        stage=PipelineStage.EXTRACTING,
        message="测试中",
        updated_at=now,
    )


@pytest.fixture(autouse=True)
def _clear_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run each test in mock mode with fresh service caches."""
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setenv("EXTRACT_TWO_PHASE_ENABLED", "false")
    get_settings.cache_clear()
    get_paper_service.cache_clear()


class TestBuildMvpInput:
    def test_prefers_head_context_when_available(self) -> None:
        head = "Title\n\nAbstract\n\nIntroduction"
        full = "\n\n".join(["Section 1"] * 100)
        result = _build_mvp_input(full, head)
        assert head in result

    def test_appends_tail_when_head_is_short(self) -> None:
        head = "Title"
        full = "Start paragraph.\n\n" + "\n\n".join(f"Paragraph {i}" for i in range(50)) + "\n\nConclusion paragraph."
        result = _build_mvp_input(full, head)
        assert "Title" in result
        assert "Conclusion paragraph" in result

    def test_falls_back_to_leading_text_when_tail_too_short(self) -> None:
        # Head absent + tail shorter than MVP_MIN_INPUT_CHARS triggers leading fallback.
        full = "Start paragraph that matters.\n\nConclusion paragraph."
        result = _build_mvp_input(full, None)
        assert "Start paragraph that matters" in result

    def test_tail_stops_at_paragraph_boundary(self) -> None:
        head = "Title"
        filler = "a" * 5000
        full = f"Start.\n\n{filler}\n\nReal conclusion that matters."
        result = _build_mvp_input(full, head)
        assert "Real conclusion that matters" in result


class TestSavePreviewGraph:
    def test_saves_preview_for_registered_paper(self) -> None:
        paper_id = "preview-save-001"
        _register_paper(paper_id)
        graph = UnifiedPaperGraph(
            paper_id=paper_id,
            paradigm=Paradigm.HSS,
            nodes=[GraphNode(id="n1", label="Thesis", type="Thesis")],
            edges=[],
        )

        _save_preview_graph(paper_id, graph)

        service = get_paper_service()
        assert service.is_preview_available(paper_id)
        assert service.get_preview_graph(paper_id) == graph
        status = service._status.get(paper_id)
        assert status is not None
        assert status.preview_available is True

    def test_skips_unregistered_paper_without_error(self) -> None:
        graph = UnifiedPaperGraph(
            paper_id="unregistered",
            paradigm=Paradigm.HSS,
            nodes=[GraphNode(id="n1", label="Thesis", type="Thesis")],
            edges=[],
        )

        _save_preview_graph("unregistered", graph)

        assert not get_paper_service().is_preview_available("unregistered")

    def test_records_warning_codes(self) -> None:
        paper_id = "preview-save-warn-001"
        _register_paper(paper_id)
        graph = UnifiedPaperGraph(
            paper_id=paper_id,
            paradigm=Paradigm.HSS,
            nodes=[GraphNode(id="n1", label="Thesis", type="Thesis")],
            edges=[],
        )

        _save_preview_graph(paper_id, graph, warnings=[MVP_SKELETON_PREVIEW_CODE])

        assert MVP_SKELETON_PREVIEW_CODE in get_paper_service().get_extract_warnings(paper_id)


class TestExtractPreviewFlag:
    @pytest.mark.asyncio
    async def test_short_text_extract_marks_preview_available(self) -> None:
        paper_id = "short-preview-001"
        _register_paper(paper_id)

        result = await extract(
            "Title: short. We study X. Method Y. Results Z.",
            Paradigm.STEM,
            paper_id=paper_id,
        )

        assert result.graph.paper_id == paper_id
        service = get_paper_service()
        assert service.is_preview_available(paper_id)
        assert service.get_preview_graph(paper_id) == result.graph

    @pytest.mark.asyncio
    async def test_long_text_extract_saves_mvp_preview_before_full(self) -> None:
        paper_id = "long-preview-001"
        _register_paper(paper_id)
        # Long text would force chunked path in live mode; mock mode still saves preview.
        long_text = "Title: long paper.\n\n" + "\n\n".join(f"Paragraph {i}: " + "x" * 1000 for i in range(50))

        result = await extract(long_text, Paradigm.HSS, paper_id=paper_id)

        service = get_paper_service()
        assert service.is_preview_available(paper_id)
        preview = service.get_preview_graph(paper_id)
        assert preview is not None
        assert preview.paper_id == paper_id
        assert preview.paradigm == Paradigm.HSS
        # Mock mode persists the final graph as the current preview.
        assert service.get_preview_graph(paper_id) == result.graph

    @pytest.mark.asyncio
    async def test_extract_without_paper_registration_does_not_crash(self) -> None:
        # Unit tests may call extract with arbitrary IDs; preview save is best-effort.
        result = await extract(
            "Title: orphan. We study X. Method Y. Results Z.",
            Paradigm.STEM,
            paper_id="orphan-paper",
        )
        assert result.graph.paper_id == "orphan-paper"
