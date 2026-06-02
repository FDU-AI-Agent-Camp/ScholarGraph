"""全链路模块交接：ingest → classify → extract → store 数据传递与调用参数。"""

from __future__ import annotations

from pathlib import Path

import pytest
from backend.graph.state import NODE_CLASSIFY, NODE_EXTRACT, NODE_INGEST, NODE_STORE
from backend.graph.workflow import run_paper_pipeline
from backend.schemas.graph import GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperStatus
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.paper_service import get_paper_service

from tests.conftest import mock_pipeline_node_services

pytestmark = pytest.mark.integration


async def test_handoff_ingest_output_feeds_classify_input(integration_paper: tuple[str, Path]) -> None:
    paper_id, pdf_path = integration_paper
    captured_classify_input: list[str] = []
    classification = ParadigmClassification(paradigm=Paradigm.HSS, confidence=0.9, reason="mock")
    graph = UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="N", type="Thesis")],
        edges=[],
    )

    with mock_pipeline_node_services(paper_id) as mocks:

        async def capture_classify(text: str) -> ParadigmClassification:
            captured_classify_input.append(text)
            return classification

        mocks["agent"].classify_paradigm.side_effect = capture_classify
        mocks["agent"].extract_graph.return_value = graph

        await run_paper_pipeline(paper_id, pdf_path)

    mocks["ingest"].ingest.assert_awaited_once()
    call_args = mocks["ingest"].ingest.await_args
    assert call_args.kwargs["paper_id"] == paper_id
    assert Path(call_args.args[0]).resolve() == pdf_path.resolve()
    assert captured_classify_input == ["classifier-input"]


async def test_handoff_classify_output_feeds_extract(integration_paper: tuple[str, Path]) -> None:
    paper_id, pdf_path = integration_paper
    captured: dict[str, object] = {}
    classification = ParadigmClassification(
        paradigm=Paradigm.STEM,
        confidence=0.88,
        reason="量化实验",
    )
    graph = UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.STEM,
        nodes=[GraphNode(id="n1", label="N", type="Method")],
        edges=[],
    )

    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["agent"].classify_paradigm.return_value = classification

        async def capture_extract(full_text: str, paradigm: Paradigm, *, paper_id: str):
            captured["full_text"] = full_text
            captured["paradigm"] = paradigm
            captured["paper_id"] = paper_id
            return graph

        mocks["agent"].extract_graph.side_effect = capture_extract
        await run_paper_pipeline(paper_id, pdf_path)

    assert captured["full_text"] == "full-text"
    assert captured["paradigm"] == Paradigm.STEM
    assert captured["paper_id"] == paper_id


async def test_handoff_extract_output_feeds_store_finalize(integration_paper: tuple[str, Path]) -> None:
    paper_id, pdf_path = integration_paper
    classification = ParadigmClassification(paradigm=Paradigm.HSS, confidence=0.9, reason="mock")
    graph = UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="Thesis", type="Thesis")],
        edges=[],
    )

    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["agent"].classify_paradigm.return_value = classification
        mocks["agent"].extract_graph.return_value = graph

        await run_paper_pipeline(paper_id, pdf_path)

    mocks["store_save"].assert_called_once()
    saved_graph = mocks["store_save"].call_args.args[0]
    assert saved_graph.paper_id == paper_id


async def test_handoff_success_updates_paper_detail_and_graph(
    integration_paper: tuple[str, Path],
) -> None:
    paper_id, pdf_path = integration_paper

    with mock_pipeline_node_services(paper_id):
        await run_paper_pipeline(paper_id, pdf_path)

    paper = await get_paper_service().get_paper(paper_id)
    assert paper.status == PaperStatus.READY
    assert paper.paradigm == Paradigm.HSS
    assert paper.classification is not None
    assert paper.classification.paradigm == Paradigm.HSS

    loaded = await get_paper_service().get_graph(paper_id)
    assert loaded.paper_id == paper_id
    assert len(loaded.nodes) >= 1


async def test_handoff_pipeline_invokes_all_four_stages_in_order(
    integration_paper: tuple[str, Path],
) -> None:
    paper_id, pdf_path = integration_paper
    order: list[str] = []

    with mock_pipeline_node_services(paper_id) as mocks:

        async def track_ingest(*_a, **_k):
            order.append(NODE_INGEST)
            return {
                "paper_id": paper_id,
                "full_text": "full-text",
                "classifier_input": "classifier-input",
            }

        async def track_classify(_t: str):
            order.append(NODE_CLASSIFY)
            return mocks["agent"].classify_paradigm.return_value

        async def track_extract(*_a, **_k):
            order.append(NODE_EXTRACT)
            return mocks["agent"].extract_graph.return_value

        mocks["ingest"].ingest.side_effect = track_ingest
        mocks["agent"].classify_paradigm.side_effect = track_classify
        mocks["agent"].extract_graph.side_effect = track_extract
        mocks["store_save"].side_effect = lambda _g: order.append(NODE_STORE)

        await run_paper_pipeline(paper_id, pdf_path)

    assert order == [NODE_INGEST, NODE_CLASSIFY, NODE_EXTRACT, NODE_STORE]
