"""Tests for PaperService.complete_pipeline quality gate decisions."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from backend.agents.extract_constants import LOW_CONFIDENCE_GRAPH_CODE
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperDetail, PaperStatus
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.paper_service import PaperService


@pytest.fixture
def service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PaperService:
    monkeypatch.setenv("GRAPH_DATA_DIR", str(tmp_path / "graphs"))
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    from backend.config import get_settings
    from backend.services.paper_service import get_paper_service

    get_settings.cache_clear()
    get_paper_service.cache_clear()
    return get_paper_service()


@pytest.fixture
def classification() -> ParadigmClassification:
    return ParadigmClassification(
        paradigm=Paradigm.HSS,
        confidence=0.9,
        reason="test",
    )


def _register_paper(service: PaperService, paper_id: str) -> None:
    now = datetime.now(UTC)
    service._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="quality gate test",
        status=PaperStatus.PROCESSING,
        created_at=now,
        updated_at=now,
    )


def _make_graph(
    paper_id: str,
    *,
    supports_with_rationale: int,
    supports_without_rationale: int,
    isolated_nodes: int,
) -> UnifiedPaperGraph:
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    idx = 0
    for _ in range(supports_with_rationale):
        src = f"n{idx}"
        nodes.append(GraphNode(id=src, label="sub", type="SubArgument"))
        idx += 1
        tgt = f"n{idx}"
        nodes.append(GraphNode(id=tgt, label="thesis", type="Thesis"))
        idx += 1
        edges.append(
            GraphEdge(
                id=f"e{len(edges)}",
                source=src,
                target=tgt,
                label="SUPPORTS",
                type="SUPPORTS",
                rationale=f"{src} -> {tgt}",
            ),
        )
    for _ in range(supports_without_rationale):
        src = f"n{idx}"
        nodes.append(GraphNode(id=src, label="sub", type="SubArgument"))
        idx += 1
        tgt = f"n{idx}"
        nodes.append(GraphNode(id=tgt, label="thesis", type="Thesis"))
        idx += 1
        edges.append(
            GraphEdge(
                id=f"e{len(edges)}",
                source=src,
                target=tgt,
                label="SUPPORTS",
                type="SUPPORTS",
                rationale=None,
            ),
        )
    for _ in range(isolated_nodes):
        nodes.append(GraphNode(id=f"n{idx}", label="iso", type="ObjectOrData"))
        idx += 1

    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=nodes,
        edges=edges,
    )


def test_complete_pipeline_marks_ready_when_quality_gate_passes(
    service: PaperService,
    classification: ParadigmClassification,
) -> None:
    paper_id = "quality-ready"
    _register_paper(service, paper_id)
    graph = _make_graph(paper_id, supports_with_rationale=2, supports_without_rationale=0, isolated_nodes=0)

    service.complete_pipeline(paper_id, classification=classification, graph=graph)

    assert service._papers[paper_id].status == PaperStatus.READY
    assert LOW_CONFIDENCE_GRAPH_CODE not in service.get_extract_warnings(paper_id)


def test_complete_pipeline_marks_ready_with_warnings_on_low_rationale(
    service: PaperService,
    classification: ParadigmClassification,
) -> None:
    paper_id = "quality-low-rationale"
    _register_paper(service, paper_id)
    graph = _make_graph(paper_id, supports_with_rationale=1, supports_without_rationale=3, isolated_nodes=0)

    service.complete_pipeline(paper_id, classification=classification, graph=graph)

    assert service._papers[paper_id].status == PaperStatus.READY_WITH_WARNINGS
    assert LOW_CONFIDENCE_GRAPH_CODE in service.get_extract_warnings(paper_id)


def test_complete_pipeline_marks_ready_with_warnings_on_high_isolation(
    service: PaperService,
    classification: ParadigmClassification,
) -> None:
    paper_id = "quality-isolated"
    _register_paper(service, paper_id)
    graph = _make_graph(paper_id, supports_with_rationale=2, supports_without_rationale=0, isolated_nodes=6)

    service.complete_pipeline(paper_id, classification=classification, graph=graph)

    assert service._papers[paper_id].status == PaperStatus.READY_WITH_WARNINGS
    assert LOW_CONFIDENCE_GRAPH_CODE in service.get_extract_warnings(paper_id)


def test_complete_pipeline_saves_graph_regardless_of_gate(
    service: PaperService,
    classification: ParadigmClassification,
) -> None:
    paper_id = "quality-saved"
    _register_paper(service, paper_id)
    graph = _make_graph(paper_id, supports_with_rationale=0, supports_without_rationale=1, isolated_nodes=0)

    service.complete_pipeline(paper_id, classification=classification, graph=graph)

    from backend.graph.store import GraphStore

    assert GraphStore().load(paper_id) is not None
