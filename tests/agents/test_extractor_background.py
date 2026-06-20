"""Tests for background extraction orchestration (Slice 2).

These tests exercise the real ``extract_preview_and_schedule_full`` and
``should_run_background_extraction`` production code while mocking the LLM
and worker boundaries so tests remain deterministic without API keys.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from backend.agents.extractor_background import (
    _minimal_pending_graph,
    extract_preview_and_schedule_full,
    should_run_background_extraction,
)
from backend.config import Settings
from backend.schemas.extract_phase import ExtractedGraph, ExtractedNode
from backend.schemas.ingest_head import IngestHead
from backend.schemas.paper import PaperDetail, PaperStatus, PaperStatusData, PipelineStage
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.paper_service import get_paper_service


def _live_settings(**overrides) -> Settings:
    defaults = {
        "_env_file": None,
        "llm_mode": "live",
        "extract_chunked_enabled": True,
        "extract_max_input_chars": 2_000,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _mock_settings(**overrides) -> Settings:
    defaults = {
        "_env_file": None,
        "llm_mode": "mock",
        "extract_chunked_enabled": True,
        "extract_max_input_chars": 2_000,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _register_paper(paper_id: str) -> None:
    service = get_paper_service()
    now = datetime.now(UTC)
    service._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="bg preview test",
        status=PaperStatus.PROCESSING,
        created_at=now,
        updated_at=now,
    )
    service._status[paper_id] = PaperStatusData(
        paper_id=paper_id,
        status=PaperStatus.PROCESSING,
        percent=50,
        stage=PipelineStage.EXTRACTING,
        message="extracting",
        updated_at=now,
    )


@pytest.fixture(autouse=True)
def _fresh_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "mock")
    from backend.config import get_settings
    from backend.services.paper_service import get_paper_service

    get_settings.cache_clear()
    get_paper_service.cache_clear()
    yield
    get_paper_service.cache_clear()


class TestShouldRunBackgroundExtraction:
    def test_mock_mode_never_runs_background(self) -> None:
        settings = _mock_settings()
        assert should_run_background_extraction("x" * 10_000, settings) is False

    def test_live_mode_long_text_runs_background(self) -> None:
        settings = _live_settings()
        assert should_run_background_extraction("x" * 10_000, settings) is True

    def test_live_mode_short_text_runs_synchronously(self) -> None:
        settings = _live_settings()
        assert should_run_background_extraction("short", settings) is False

    def test_live_mode_chunked_disabled_runs_synchronously(self) -> None:
        settings = _live_settings(extract_chunked_enabled=False)
        assert should_run_background_extraction("x" * 10_000, settings) is False

    def test_exact_threshold_boundary(self) -> None:
        settings = _live_settings(extract_max_input_chars=100)
        assert should_run_background_extraction("x" * 100, settings) is False
        assert should_run_background_extraction("x" * 101, settings) is True


class TestMinimalPendingGraph:
    def test_hss_pending_node_type(self) -> None:
        graph = _minimal_pending_graph("p1", "title", Paradigm.HSS)
        assert graph.paper_id == "p1"
        assert graph.title == "title"
        assert len(graph.nodes) == 1
        assert graph.nodes[0].type == "Thesis"

    def test_stem_pending_node_type(self) -> None:
        graph = _minimal_pending_graph("p2", "title", Paradigm.STEM)
        assert graph.nodes[0].type == "ResearchQuestion"


class TestExtractPreviewAndScheduleFull:
    async def test_returns_preview_when_mvp_succeeds(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        paper_id = "bg-preview-001"
        _register_paper(paper_id)
        settings = _mock_settings()

        mvp_graph = ExtractedGraph(
            paper_id=paper_id,
            title="preview",
            paradigm=Paradigm.HSS,
            nodes=[ExtractedNode(id="n1", label="Preview Node", type="Thesis")],
            edges=[],
            summary="mvp",
        )

        scheduled_calls: list[tuple[tuple, dict]] = []

        async def fake_extract_mvp(*args, **kwargs) -> ExtractedGraph:
            return mvp_graph

        def fake_schedule_full_extraction(*args, **kwargs) -> object:
            scheduled_calls.append((args, kwargs))
            return MagicMock()

        monkeypatch.setattr(
            "backend.agents.extractor_background._extract_mvp",
            fake_extract_mvp,
        )
        monkeypatch.setattr(
            "backend.services.extract_worker.schedule_full_extraction",
            fake_schedule_full_extraction,
        )

        result = await extract_preview_and_schedule_full(
            "long text " * 500,
            Paradigm.HSS,
            paper_id=paper_id,
            classification=ParadigmClassification(
                paradigm=Paradigm.HSS,
                confidence=0.9,
                reason="test",
            ),
            settings=settings,
        )

        assert result.warnings == ["mvp_skeleton_preview"]
        assert result.graph.paper_id == paper_id
        assert any(n.id == "n1" for n in result.graph.nodes)
        assert len(scheduled_calls) == 1
        args, kwargs = scheduled_calls[0]
        assert args[0] == paper_id

    async def test_schedules_full_even_when_mvp_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        paper_id = "bg-preview-002"
        _register_paper(paper_id)
        settings = _mock_settings()

        scheduled_calls: list[tuple[tuple, dict]] = []

        async def failing_extract_mvp(*args, **kwargs) -> ExtractedGraph:
            raise RuntimeError("mvp llm failed")

        def fake_schedule_full_extraction(*args, **kwargs) -> object:
            scheduled_calls.append((args, kwargs))
            return MagicMock()

        monkeypatch.setattr(
            "backend.agents.extractor_background._extract_mvp",
            failing_extract_mvp,
        )
        monkeypatch.setattr(
            "backend.services.extract_worker.schedule_full_extraction",
            fake_schedule_full_extraction,
        )

        result = await extract_preview_and_schedule_full(
            "long text " * 500,
            Paradigm.HSS,
            paper_id=paper_id,
            classification=ParadigmClassification(
                paradigm=Paradigm.HSS,
                confidence=0.9,
                reason="test",
            ),
            settings=settings,
        )

        assert result.warnings == ["mvp_skeleton_preview"]
        assert result.graph.paper_id == paper_id
        assert result.graph.nodes[0].label == "后台全量抽取中"
        assert len(scheduled_calls) == 1

    async def test_passes_head_context_to_worker(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        paper_id = "bg-preview-003"
        _register_paper(paper_id)
        get_paper_service().apply_head_refine(
            paper_id,
            merged=IngestHead(title="T", abstract="A", intro="I"),
            classifier_input="T A I",
        )
        settings = _mock_settings()

        scheduled_calls: list[tuple[tuple, dict]] = []

        async def fake_extract_mvp(*args, **kwargs) -> ExtractedGraph:
            return ExtractedGraph(
                paper_id=paper_id,
                title="preview",
                paradigm=Paradigm.HSS,
                nodes=[ExtractedNode(id="n1", label="N", type="Thesis")],
                edges=[],
                summary="mvp",
            )

        def fake_schedule_full_extraction(*args, **kwargs) -> object:
            scheduled_calls.append((args, kwargs))
            return MagicMock()

        monkeypatch.setattr(
            "backend.agents.extractor_background._extract_mvp",
            fake_extract_mvp,
        )
        monkeypatch.setattr(
            "backend.services.extract_worker.schedule_full_extraction",
            fake_schedule_full_extraction,
        )

        await extract_preview_and_schedule_full(
            "long text " * 500,
            Paradigm.HSS,
            paper_id=paper_id,
            classification=ParadigmClassification(
                paradigm=Paradigm.HSS,
                confidence=0.9,
                reason="test",
            ),
            settings=settings,
        )

        args, kwargs = scheduled_calls[0]
        head_context = kwargs.get("head_context")
        assert head_context is not None
        assert "T" in head_context
        assert "A" in head_context
