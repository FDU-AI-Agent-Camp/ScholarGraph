"""Unit tests: per-node inputs, outputs, and progress side effects."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from backend.graph import nodes
from backend.graph.state import WorkflowState
from backend.schemas.graph import GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.errors import ServiceError
from backend.services.graph_persistence_service import GraphPersistenceService
from backend.services.paper_service import get_paper_service
from backend.services.pipeline_completion_service import PipelineCompletionService

# ── ingest_node ─────────────────────────────────────────────────────────────


async def test_ingest_node_writes_full_text_and_classifier_input(
    workflow_initial_state: WorkflowState,
    workflow_paper: tuple[str, Path],
) -> None:
    paper_id, pdf_path = workflow_paper
    ingest_svc = MagicMock()
    ingest_svc.ingest = AsyncMock(
        return_value={
            "paper_id": paper_id,
            "full_text": "BODY",
            "classifier_input": "SNIPPET",
        },
    )
    with patch("backend.graph.nodes.get_ingest_service", return_value=ingest_svc):
        out = await nodes.ingest_node(workflow_initial_state)

    ingest_svc.ingest.assert_awaited_once_with(pdf_path, paper_id=paper_id)
    assert out["full_text"] == "BODY"
    assert out["classifier_input"] == "SNIPPET"
    assert out.get("failed") is False
    assert out["stage"] == PipelineStage.INGESTING

    status = await get_paper_service().get_status(paper_id)
    assert status.stage == PipelineStage.INGESTING
    assert status.status == PaperStatus.PROCESSING


async def test_ingest_node_service_error_sets_failed_patch(
    workflow_initial_state: WorkflowState,
) -> None:
    ingest_svc = MagicMock()
    ingest_svc.ingest = AsyncMock(
        side_effect=ServiceError("PIPELINE_FAILED", "BE-1 pending"),
    )
    with patch("backend.graph.nodes.get_ingest_service", return_value=ingest_svc):
        out = await nodes.ingest_node(workflow_initial_state)

    assert out["failed"] is True
    assert out["error_code"] == "PIPELINE_FAILED"
    assert "BE-1 pending" in out["error_message"]


async def test_ingest_node_ingest_failed_code_from_service(
    workflow_initial_state: WorkflowState,
) -> None:
    ingest_svc = MagicMock()
    ingest_svc.ingest = AsyncMock(
        side_effect=ServiceError("INGEST_FAILED", "PDF 解析失败: corrupt pdf"),
    )
    with patch("backend.graph.nodes.get_ingest_service", return_value=ingest_svc):
        out = await nodes.ingest_node(workflow_initial_state)

    assert out["error_code"] == "INGEST_FAILED"


# ── wait_head_refine_node ───────────────────────────────────────────────────


async def test_wait_head_refine_node_replaces_classifier_input(
    post_ingest_state: WorkflowState,
) -> None:
    with (
        patch("backend.graph.nodes.ensure_head_refine_scheduled") as mock_schedule,
        patch(
            "backend.graph.nodes.wait_for_refined_classifier_input",
            new=AsyncMock(return_value=("REFINED-INPUT", ["grobid_unavailable"])),
        ),
    ):
        out = await nodes.wait_head_refine_node(post_ingest_state)

    mock_schedule.assert_called_once_with(
        post_ingest_state["paper_id"],
        Path(post_ingest_state["pdf_path"]),
    )
    assert out["classifier_input"] == "REFINED-INPUT"
    assert out["head_refine_warnings"] == ["grobid_unavailable"]
    assert out["stage"] == PipelineStage.HEAD_REFINING
    assert out.get("failed") is False


async def test_wait_head_refine_node_marks_progress_message(
    post_ingest_state: WorkflowState,
    workflow_paper: tuple[str, Path],
) -> None:
    from backend.services.pipeline_status_service import get_pipeline_status_service

    paper_id, _ = workflow_paper
    get_pipeline_status_service().start_processing(paper_id)
    with (
        patch("backend.graph.nodes.ensure_head_refine_scheduled"),
        patch(
            "backend.graph.nodes.wait_for_refined_classifier_input",
            new=AsyncMock(return_value=("REFINED", [])),
        ),
    ):
        await nodes.wait_head_refine_node(post_ingest_state)

    status = await get_paper_service().get_status(paper_id)
    assert status.stage == PipelineStage.HEAD_REFINING
    assert "精炼" in status.message


async def test_wait_head_refine_node_preserves_full_text_in_state(
    post_ingest_state: WorkflowState,
) -> None:
    post_ingest_state["full_text"] = "FULL-BODY-UNTOUCHED"
    with (
        patch("backend.graph.nodes.ensure_head_refine_scheduled"),
        patch(
            "backend.graph.nodes.wait_for_refined_classifier_input",
            new=AsyncMock(return_value=("REFINED", [])),
        ),
    ):
        out = await nodes.wait_head_refine_node(post_ingest_state)

    assert post_ingest_state["full_text"] == "FULL-BODY-UNTOUCHED"
    assert "full_text" not in out


async def test_classify_node_receives_refined_classifier_input(
    post_ingest_state: WorkflowState,
) -> None:
    classification = ParadigmClassification(
        paradigm=Paradigm.HSS,
        confidence=0.9,
        reason="mock",
    )
    agent_svc = MagicMock()
    agent_svc.classify_paradigm = AsyncMock(return_value=classification)

    state = dict(post_ingest_state)
    state["classifier_input"] = "REFINED-INPUT"

    with patch("backend.graph.nodes.get_agent_service", return_value=agent_svc):
        await nodes.classify_node(WorkflowState(**state))

    agent_svc.classify_paradigm.assert_awaited_once_with("REFINED-INPUT")


# ── classify_node ───────────────────────────────────────────────────────────


async def test_classify_node_maps_classification_to_state(
    post_ingest_state: WorkflowState,
) -> None:
    classification = ParadigmClassification(
        paradigm=Paradigm.STEM,
        confidence=0.88,
        reason="含实验与指标",
    )
    agent_svc = MagicMock()
    agent_svc.classify_paradigm = AsyncMock(return_value=classification)
    with patch("backend.graph.nodes.get_agent_service", return_value=agent_svc):
        out = await nodes.classify_node(post_ingest_state)

    agent_svc.classify_paradigm.assert_awaited_once_with("Title\nAbstract\nKeywords")
    assert out["paradigm"] == Paradigm.STEM.value
    assert out["classification"]["paradigm"] == "STEM"
    assert out.get("failed") is False


async def test_classify_node_service_error_sets_llm_json_invalid(
    post_ingest_state: WorkflowState,
) -> None:
    agent_svc = MagicMock()
    agent_svc.classify_paradigm = AsyncMock(
        side_effect=ServiceError("LLM_JSON_INVALID", "范式分类失败: invalid json"),
    )
    with patch("backend.graph.nodes.get_agent_service", return_value=agent_svc):
        out = await nodes.classify_node(post_ingest_state)

    assert out["failed"] is True
    assert out["error_code"] == "LLM_JSON_INVALID"


# ── extract_node ────────────────────────────────────────────────────────────


async def test_extract_node_delegates_to_agent_service(
    post_classify_state: WorkflowState,
) -> None:
    graph = UnifiedPaperGraph(
        paper_id=post_classify_state["paper_id"],
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="L", type="Thesis")],
        edges=[],
    )
    from backend.agents.extract_types import ExtractResult

    agent_svc = MagicMock()
    agent_svc.extract_graph = AsyncMock(return_value=ExtractResult(graph=graph, warnings=[]))
    with patch("backend.graph.nodes.get_agent_service", return_value=agent_svc):
        out = await nodes.extract_node(post_classify_state)

    agent_svc.extract_graph.assert_awaited_once_with(
        "Full paper body text.",
        Paradigm.HSS,
        paper_id=post_classify_state["paper_id"],
    )
    assert out["graph"]["paper_id"] == post_classify_state["paper_id"]
    assert out.get("failed") is False


async def test_extract_node_records_extract_warnings(
    post_classify_state: WorkflowState,
) -> None:
    from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE
    from backend.agents.extract_types import ExtractResult

    graph = UnifiedPaperGraph(
        paper_id=post_classify_state["paper_id"],
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="L", type="Thesis")],
        edges=[],
    )
    agent_svc = MagicMock()
    agent_svc.extract_graph = AsyncMock(
        return_value=ExtractResult(graph=graph, warnings=[EXTRACT_HEURISTIC_FALLBACK_CODE]),
    )
    paper_svc = MagicMock()

    with (
        patch("backend.graph.nodes.get_agent_service", return_value=agent_svc),
        patch("backend.graph.nodes.get_paper_service", return_value=paper_svc),
    ):
        out = await nodes.extract_node(post_classify_state)

    paper_svc.record_extract_warnings.assert_called_once_with(
        post_classify_state["paper_id"],
        [EXTRACT_HEURISTIC_FALLBACK_CODE],
    )
    assert out["extract_warnings"] == [EXTRACT_HEURISTIC_FALLBACK_CODE]


# ── store_node ──────────────────────────────────────────────────────────────


async def test_store_node_delegates_finalize_to_completion_service(
    post_extract_state: WorkflowState,
) -> None:
    paper_id = post_extract_state["paper_id"]
    with patch("backend.services.graph_persistence_service.GraphStore") as store_cls:
        store_cls.return_value.save = MagicMock()
        persistence = GraphPersistenceService(store=store_cls.return_value)
        completion_svc = PipelineCompletionService(graph_persistence=persistence)
        with patch(
            "backend.graph.nodes.get_pipeline_completion_service",
            return_value=completion_svc,
        ):
            out = await nodes.store_node(post_extract_state)

    store_cls.return_value.save.assert_called_once()
    assert out["status"] == PaperStatus.READY

    paper = await get_paper_service().get_paper(paper_id)
    assert paper.status == PaperStatus.READY


async def test_store_node_finalize_error_fails(
    post_extract_state: WorkflowState,
) -> None:
    completion_svc = MagicMock()
    completion_svc.finalize = MagicMock(
        side_effect=ServiceError("PIPELINE_FAILED", "建图收尾失败: bad graph"),
    )
    with patch("backend.graph.nodes.get_pipeline_completion_service", return_value=completion_svc):
        out = await nodes.store_node(post_extract_state)

    assert out["failed"] is True
    assert "建图收尾失败" in out["error_message"]


# ── fail_node ───────────────────────────────────────────────────────────────


async def test_fail_node_updates_paper_status_to_failed(
    workflow_paper: tuple[str, Path],
) -> None:
    paper_id, _ = workflow_paper
    state = WorkflowState(
        paper_id=paper_id,
        stage=PipelineStage.INGESTING,
        error_code="INGEST_FAILED",
        error_message="无法解析 PDF",
        message="无法解析 PDF",
        failed=True,
    )
    out = await nodes.fail_node(state)

    assert out["status"] == PaperStatus.FAILED
    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.FAILED
    assert status.error_code == "INGEST_FAILED"
    assert status.failed_during == PipelineStage.INGESTING
