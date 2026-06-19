"""Tests for PaperService preview-graph lifecycle (Slice 1)."""

from __future__ import annotations

import pytest
from backend.api.exceptions import ApiError
from backend.graph.store import GraphStore
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperDetail, PaperStatus, PaperStatusData, PipelineStage
from backend.schemas.paradigm import Paradigm
from backend.services.paper_service import get_paper_service


def _make_paper(paper_id: str, status: PaperStatus = PaperStatus.PROCESSING) -> PaperDetail:
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    return PaperDetail(
        paper_id=paper_id,
        title="preview service test",
        status=status,
        created_at=now,
        updated_at=now,
    )


def _make_status(paper_id: str, status: PaperStatus = PaperStatus.PROCESSING) -> PaperStatusData:
    from datetime import UTC, datetime

    return PaperStatusData(
        paper_id=paper_id,
        status=status,
        percent=10,
        stage=PipelineStage.EXTRACTING,
        message="测试中",
        updated_at=datetime.now(UTC),
    )


@pytest.fixture(autouse=True)
def _fresh_service() -> None:
    get_paper_service.cache_clear()
    yield
    get_paper_service.cache_clear()


class TestPreviewStorage:
    def test_save_preview_graph_for_existing_paper(self) -> None:
        service = get_paper_service()
        paper_id = "ps-preview-001"
        service._papers[paper_id] = _make_paper(paper_id)
        graph = UnifiedPaperGraph(
            paper_id=paper_id,
            paradigm=Paradigm.HSS,
            nodes=[GraphNode(id="n1", label="Thesis", type="Thesis")],
            edges=[],
        )

        service.save_preview_graph(paper_id, graph)

        assert service.get_preview_graph(paper_id) == graph

    def test_save_preview_graph_for_missing_paper_raises(self) -> None:
        service = get_paper_service()
        graph = UnifiedPaperGraph(
            paper_id="missing",
            paradigm=Paradigm.HSS,
            nodes=[],
            edges=[],
        )

        with pytest.raises(ApiError) as exc_info:
            service.save_preview_graph("missing", graph)
        assert exc_info.value.code == "PAPER_NOT_FOUND"

    def test_mark_preview_available_updates_status_snapshot(self) -> None:
        service = get_paper_service()
        paper_id = "ps-mark-001"
        service._papers[paper_id] = _make_paper(paper_id)
        service._status[paper_id] = _make_status(paper_id)

        service.mark_preview_available(paper_id)

        assert service.is_preview_available(paper_id)
        assert service._status[paper_id].preview_available is True


class TestGetGraphPreview:
    async def test_get_graph_returns_preview_when_not_ready(self) -> None:
        service = get_paper_service()
        paper_id = "ps-graph-preview-001"
        service._papers[paper_id] = _make_paper(paper_id, status=PaperStatus.PROCESSING)
        service._status[paper_id] = _make_status(paper_id)
        service.mark_preview_available(paper_id)
        graph = UnifiedPaperGraph(
            paper_id=paper_id,
            paradigm=Paradigm.STEM,
            nodes=[GraphNode(id="n1", label="Method", type="Method")],
            edges=[],
        )
        service.save_preview_graph(paper_id, graph)

        result = await service.get_graph(paper_id)

        assert result == graph

    async def test_get_graph_returns_full_graph_when_ready(self) -> None:
        service = get_paper_service()
        paper_id = "ps-graph-ready-001"
        service._papers[paper_id] = _make_paper(paper_id, status=PaperStatus.READY)
        preview = UnifiedPaperGraph(
            paper_id=paper_id,
            paradigm=Paradigm.STEM,
            nodes=[GraphNode(id="n1", label="Preview", type="Method")],
            edges=[],
        )
        full = UnifiedPaperGraph(
            paper_id=paper_id,
            paradigm=Paradigm.STEM,
            nodes=[
                GraphNode(id="n1", label="Method", type="Method"),
                GraphNode(id="n2", label="Finding", type="Finding"),
            ],
            edges=[GraphEdge(id="e1", source="n1", target="n2", label="produces", type="PRODUCES")],
        )
        service.save_preview_graph(paper_id, preview)
        GraphStore().save(full)

        result = await service.get_graph(paper_id)

        assert result == full

    async def test_get_graph_raises_when_processing_without_preview(self) -> None:
        service = get_paper_service()
        paper_id = "ps-graph-none-001"
        service._papers[paper_id] = _make_paper(paper_id, status=PaperStatus.PROCESSING)
        service._status[paper_id] = _make_status(paper_id)

        with pytest.raises(ApiError) as exc_info:
            await service.get_graph(paper_id)
        assert exc_info.value.code == "GRAPH_NOT_READY"


class TestPreviewDetailEnrichment:
    async def test_get_paper_includes_preview_available(self) -> None:
        service = get_paper_service()
        paper_id = "ps-detail-001"
        service._papers[paper_id] = _make_paper(paper_id, status=PaperStatus.PROCESSING)
        service.mark_preview_available(paper_id)

        paper = await service.get_paper(paper_id)

        assert paper.preview_available is True

    async def test_get_status_includes_preview_available(self) -> None:
        service = get_paper_service()
        paper_id = "ps-status-001"
        service._papers[paper_id] = _make_paper(paper_id, status=PaperStatus.PROCESSING)
        service._status[paper_id] = _make_status(paper_id)
        service.mark_preview_available(paper_id)

        status = await service.get_status(paper_id)

        assert status.preview_available is True


class TestPreviewWarnings:
    def test_record_and_retrieve_warnings(self) -> None:
        service = get_paper_service()
        paper_id = "ps-warning-001"
        service._papers[paper_id] = _make_paper(paper_id)

        service.record_extract_warnings(paper_id, ["low_quality_text"])

        assert service.get_extract_warnings(paper_id) == ["low_quality_text"]

    @pytest.mark.red
    def test_record_warnings_for_missing_paper_should_raise(self) -> None:
        """Red test: warning recording should validate paper existence.

        Currently ``record_extract_warnings`` silently accepts unknown IDs.
        This test documents the desired defensive contract.
        """
        service = get_paper_service()

        with pytest.raises(ApiError) as exc_info:
            service.record_extract_warnings("missing", ["low_quality_text"])
        assert exc_info.value.code == "PAPER_NOT_FOUND"
