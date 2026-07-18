# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Tests for PaperService.complete_pipeline quality gate decisions."""

from __future__ import annotations

import pytest
from backend.agents.extract_constants import LOW_CONFIDENCE_GRAPH_CODE
from backend.graph.store import GraphStore
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperStatus
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.paper_service import get_paper_service
from backend.services.paper_warning_service import WarningType, get_paper_warning_service
from tests.helpers.event_bus_testkit import drain_event_bus
from tests.helpers.persistence_testkit import register_test_paper


@pytest.fixture
def service(persistence_env):
    from backend.services.paper_service import reset_persistence_singletons

    reset_persistence_singletons()
    return get_paper_service()


@pytest.fixture
def classification() -> ParadigmClassification:
    return ParadigmClassification(
        paradigm=Paradigm.HSS,
        confidence=0.9,
        reason="test",
    )


async def _register_paper(paper_id: str) -> None:
    await register_test_paper(paper_id, status=PaperStatus.PROCESSING)


def _make_graph(
    paper_id: str,
    *,
    supports_with_rationale: int,
    supports_without_rationale: int,
    isolated_nodes: int,
    generic_edges: int = 0,
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

    for _ in range(generic_edges):
        src = f"n{idx}"
        nodes.append(GraphNode(id=src, label="src", type="SubArgument"))
        idx += 1
        tgt = f"n{idx}"
        nodes.append(GraphNode(id=tgt, label="tgt", type="Thesis"))
        idx += 1
        edges.append(
            GraphEdge(
                id=f"e{len(edges)}",
                source=src,
                target=tgt,
                label="RELATES_TO",
                type="RELATES_TO",
            ),
        )

    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=nodes,
        edges=edges,
    )


@pytest.mark.asyncio
async def test_complete_pipeline_marks_ready_when_quality_gate_passes(
    service,
    classification: ParadigmClassification,
) -> None:
    paper_id = "quality-ready"
    await _register_paper(paper_id)
    graph = _make_graph(paper_id, supports_with_rationale=2, supports_without_rationale=0, isolated_nodes=0)

    await service.complete_pipeline(paper_id, classification=classification, graph=graph)
    await drain_event_bus()

    paper = await service.get_paper(paper_id)
    assert paper.status == PaperStatus.READY
    assert LOW_CONFIDENCE_GRAPH_CODE not in await get_paper_warning_service().get(paper_id, WarningType.EXTRACT)


@pytest.mark.asyncio
async def test_complete_pipeline_marks_ready_with_warnings_on_low_rationale(
    service,
    classification: ParadigmClassification,
) -> None:
    paper_id = "quality-low-rationale"
    await _register_paper(paper_id)
    graph = _make_graph(paper_id, supports_with_rationale=1, supports_without_rationale=3, isolated_nodes=0)

    await service.complete_pipeline(paper_id, classification=classification, graph=graph)
    await drain_event_bus()

    paper = await service.get_paper(paper_id)
    assert paper.status == PaperStatus.READY_WITH_WARNINGS
    assert LOW_CONFIDENCE_GRAPH_CODE in await get_paper_warning_service().get(paper_id, WarningType.EXTRACT)


@pytest.mark.asyncio
async def test_complete_pipeline_marks_ready_with_warnings_on_high_isolation(
    service,
    classification: ParadigmClassification,
) -> None:
    paper_id = "quality-isolated"
    await _register_paper(paper_id)
    graph = _make_graph(paper_id, supports_with_rationale=2, supports_without_rationale=0, isolated_nodes=6)

    await service.complete_pipeline(paper_id, classification=classification, graph=graph)
    await drain_event_bus()

    paper = await service.get_paper(paper_id)
    assert paper.status == PaperStatus.READY_WITH_WARNINGS
    assert LOW_CONFIDENCE_GRAPH_CODE in await get_paper_warning_service().get(paper_id, WarningType.EXTRACT)


@pytest.mark.asyncio
async def test_complete_pipeline_marks_ready_with_warnings_on_high_generic_edge_ratio(
    service,
    classification: ParadigmClassification,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paper_id = "quality-generic"
    await _register_paper(paper_id)
    graph = _make_graph(
        paper_id,
        supports_with_rationale=2,
        supports_without_rationale=0,
        isolated_nodes=0,
        generic_edges=2,
    )

    from backend.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "extract_max_generic_edge_ratio", 0.3)

    await service.complete_pipeline(paper_id, classification=classification, graph=graph)
    await drain_event_bus()

    paper = await service.get_paper(paper_id)
    assert paper.status == PaperStatus.READY_WITH_WARNINGS
    assert LOW_CONFIDENCE_GRAPH_CODE in await get_paper_warning_service().get(paper_id, WarningType.EXTRACT)


@pytest.mark.asyncio
async def test_complete_pipeline_saves_graph_regardless_of_gate(
    service,
    classification: ParadigmClassification,
    persistence_env,
) -> None:
    paper_id = "quality-saved"
    await _register_paper(paper_id)
    graph = _make_graph(paper_id, supports_with_rationale=0, supports_without_rationale=1, isolated_nodes=0)

    await service.complete_pipeline(paper_id, classification=classification, graph=graph)

    assert GraphStore(base_dir=persistence_env["graph_dir"]).load(paper_id) is not None
