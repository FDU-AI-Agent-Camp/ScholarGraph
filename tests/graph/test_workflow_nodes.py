"""Unit tests: per-node inputs, outputs, and progress side effects."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from backend.graph import nodes
from backend.graph.state import STAGE_PERCENT, WorkflowState
from backend.schemas.graph import GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.paper_service import get_paper_service


# ── ingest_node ─────────────────────────────────────────────────────────────


async def test_ingest_node_writes_full_text_and_classifier_input(
    workflow_initial_state: WorkflowState,
    workflow_paper: tuple[str, Path],
) -> None:
    paper_id, pdf_path = workflow_paper
    with patch("backend.graph.nodes.ingest_pdf", new_callable=AsyncMock) as ingest:
        ingest.return_value = {
            "paper_id": paper_id,
            "full_text": "BODY",
            "classifier_input": "SNIPPET",
        }
        out = await nodes.ingest_node(workflow_initial_state)

    ingest.assert_awaited_once_with(pdf_path, paper_id=paper_id)
    assert out["full_text"] == "BODY"
    assert out["classifier_input"] == "SNIPPET"
    assert out.get("failed") is False
    assert out["stage"] == PipelineStage.INGESTING
    assert out["percent"] == STAGE_PERCENT[PipelineStage.INGESTING]

    status = await get_paper_service().get_status(paper_id)
    assert status.stage == PipelineStage.INGESTING
    assert status.status == PaperStatus.PROCESSING


async def test_ingest_node_not_implemented_sets_failed_patch(
    workflow_initial_state: WorkflowState,
) -> None:
    with patch("backend.graph.nodes.ingest_pdf", new_callable=AsyncMock) as ingest:
        ingest.side_effect = NotImplementedError("BE-1 pending")
        out = await nodes.ingest_node(workflow_initial_state)

    assert out["failed"] is True
    assert out["error_code"] == nodes.PIPELINE_FAILED_CODE
    assert "BE-1 pending" in out["error_message"]
    assert out["stage"] == PipelineStage.INGESTING


async def test_ingest_node_generic_error_uses_ingest_failed_code(
    workflow_initial_state: WorkflowState,
) -> None:
    with patch("backend.graph.nodes.ingest_pdf", new_callable=AsyncMock) as ingest:
        ingest.side_effect = ValueError("corrupt pdf")
        out = await nodes.ingest_node(workflow_initial_state)

    assert out["failed"] is True
    assert out["error_code"] == "INGEST_FAILED"
    assert "corrupt pdf" in out["error_message"]


# ── classify_node ───────────────────────────────────────────────────────────


async def test_classify_node_maps_classification_to_state(
    post_ingest_state: WorkflowState,
) -> None:
    classification = ParadigmClassification(
        paradigm=Paradigm.STEM,
        confidence=0.88,
        reason="含实验与指标",
    )
    with patch("backend.graph.nodes.classify", new_callable=AsyncMock) as classify:
        classify.return_value = classification
        out = await nodes.classify_node(post_ingest_state)

    classify.assert_awaited_once_with("Title\nAbstract\nKeywords")
    assert out["paradigm"] == Paradigm.STEM.value
    assert out["classification"]["paradigm"] == "STEM"
    assert out["classification"]["confidence"] == 0.88
    assert out.get("failed") is False

    status = await get_paper_service().get_status(post_ingest_state["paper_id"])
    assert status.stage == PipelineStage.CLASSIFYING


async def test_classify_node_llm_failure_sets_llm_json_invalid(
    post_ingest_state: WorkflowState,
) -> None:
    with patch("backend.graph.nodes.classify", new_callable=AsyncMock) as classify:
        classify.side_effect = RuntimeError("invalid json")
        out = await nodes.classify_node(post_ingest_state)

    assert out["failed"] is True
    assert out["error_code"] == "LLM_JSON_INVALID"
    assert out["stage"] == PipelineStage.CLASSIFYING


# ── extract_node ────────────────────────────────────────────────────────────


async def test_extract_node_passes_text_and_paradigm(
    post_classify_state: WorkflowState,
) -> None:
    graph = UnifiedPaperGraph(
        paper_id="other",
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="L", type="Thesis")],
        edges=[],
    )
    with patch("backend.graph.nodes.extract", new_callable=AsyncMock) as extract:
        extract.return_value = graph
        out = await nodes.extract_node(post_classify_state)

    extract.assert_awaited_once_with("Full paper body text.", Paradigm.HSS)
    assert out["graph"]["paper_id"] == post_classify_state["paper_id"]
    assert out["graph"]["paradigm"] == Paradigm.HSS.value
    assert out.get("failed") is False


async def test_extract_node_not_implemented_marks_failed(
    post_classify_state: WorkflowState,
) -> None:
    with patch("backend.graph.nodes.extract", new_callable=AsyncMock) as extract:
        extract.side_effect = NotImplementedError("BE-2 pending")
        out = await nodes.extract_node(post_classify_state)

    assert out["failed"] is True
    assert out["stage"] == PipelineStage.EXTRACTING


# ── store_node ──────────────────────────────────────────────────────────────


async def test_store_node_persists_graph_and_completes_paper(
    post_extract_state: WorkflowState,
) -> None:
    paper_id = post_extract_state["paper_id"]
    saved: list[UnifiedPaperGraph] = []

    with patch("backend.graph.nodes.GraphStore") as store_cls:
        store_cls.return_value.save = lambda graph: saved.append(graph)
        out = await nodes.store_node(post_extract_state)

    assert len(saved) == 1
    assert saved[0].paper_id == paper_id
    assert out["status"] == PaperStatus.READY
    assert out["stage"] == PipelineStage.READY

    paper = await get_paper_service().get_paper(paper_id)
    assert paper.status == PaperStatus.READY
    assert paper.classification is not None
    assert paper.paradigm == Paradigm.HSS


async def test_store_node_invalid_graph_payload_fails(
    post_extract_state: WorkflowState,
) -> None:
    broken = dict(post_extract_state)
    broken["graph"] = {"paper_id": "x", "nodes": "not-a-list"}
    out = await nodes.store_node(WorkflowState(**broken))

    assert out["failed"] is True
    assert out["error_code"] == nodes.PIPELINE_FAILED_CODE
    assert "图谱存储失败" in out["error_message"]


# ── fail_node ───────────────────────────────────────────────────────────────


async def test_fail_node_updates_paper_status_to_failed(
    workflow_paper: tuple[str, Path],
) -> None:
    paper_id, _ = workflow_paper
    state = WorkflowState(
        paper_id=paper_id,
        error_code="INGEST_FAILED",
        error_message="无法解析 PDF",
        message="无法解析 PDF",
        failed=True,
    )
    out = await nodes.fail_node(state)

    assert out["status"] == PaperStatus.FAILED
    assert out["stage"] == PipelineStage.FAILED
    assert out["percent"] == 0

    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.FAILED
    assert status.message == "无法解析 PDF"
