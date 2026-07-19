# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Unit tests: per-node inputs, outputs, and progress side effects."""

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from backend.agents.classifier_constants import CLASSIFIER_HEURISTIC_FALLBACK_CODE
from backend.agents.classifier_types import ClassifyResult
from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE
from backend.graph import nodes
from backend.graph.state import WorkflowState
from backend.schemas.graph import GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.agent_service import AgentService
from backend.services.errors import ServiceError
from backend.services.graph_persistence_service import GraphPersistenceService
from backend.services.paper_service import get_paper_service
from backend.services.paper_warning_service import WarningType, get_paper_warning_service
from backend.services.pipeline_completion_service import PipelineCompletionService

from tests.helpers.event_bus_testkit import drain_event_bus

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
    agent_svc.classify_paradigm = AsyncMock(return_value=ClassifyResult(classification=classification, warnings=[]))

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
    agent_svc.classify_paradigm = AsyncMock(return_value=ClassifyResult(classification=classification, warnings=[]))
    with patch("backend.graph.nodes.get_agent_service", return_value=agent_svc):
        out = await nodes.classify_node(post_ingest_state)

    agent_svc.classify_paradigm.assert_awaited_once_with("Title\nAbstract\nKeywords")
    assert out["paradigm"] == Paradigm.STEM.value
    assert out["classification"]["paradigm"] == "STEM"
    assert out.get("failed") is False


async def test_classify_node_records_classify_warnings(
    post_ingest_state: WorkflowState,
) -> None:
    classification = ParadigmClassification(
        paradigm=Paradigm.HSS,
        confidence=0.9,
        reason="mock",
    )
    agent_svc = MagicMock()
    agent_svc.classify_paradigm = AsyncMock(
        return_value=ClassifyResult(
            classification=classification,
            warnings=[CLASSIFIER_HEURISTIC_FALLBACK_CODE],
        ),
    )
    paper_id = post_ingest_state["paper_id"]
    warning_service = get_paper_warning_service()
    with (
        patch("backend.graph.nodes.get_agent_service", return_value=agent_svc),
        patch.object(
            warning_service,
            "record",
            wraps=warning_service.record,
        ) as record_warnings,
    ):
        out = await nodes.classify_node(post_ingest_state)

    record_warnings.assert_awaited_once_with(
        paper_id,
        WarningType.CLASSIFY,
        [CLASSIFIER_HEURISTIC_FALLBACK_CODE],
    )
    assert out["classify_warnings"] == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]


async def test_g23_classify_node_llm_failure_persists_warnings_without_failed(
    post_ingest_state: WorkflowState,
    live_classify_env: None,
) -> None:
    """G2.3: real AgentService + LLM fail → heuristic; pipeline state not failed."""
    _ = live_classify_env
    agent = AgentService()
    paper_id = post_ingest_state["paper_id"]

    with (
        patch("backend.graph.nodes.get_agent_service", return_value=agent),
        patch(
            "backend.agents.classifier.classify_with_llm",
            new=AsyncMock(side_effect=RuntimeError("structured output failed")),
        ),
    ):
        out = await nodes.classify_node(post_ingest_state)

    assert out.get("failed") is not True
    assert CLASSIFIER_HEURISTIC_FALLBACK_CODE in out["classify_warnings"]
    assert await get_paper_warning_service().get(paper_id, WarningType.CLASSIFY) == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]
    assert out["paradigm"] in (Paradigm.STEM.value, Paradigm.HSS.value)


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
    agent_svc.should_extract_in_background = MagicMock(return_value=False)
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
    agent_svc.should_extract_in_background = MagicMock(return_value=False)
    warning_service = MagicMock()
    warning_service.record = AsyncMock()

    with (
        patch("backend.graph.nodes.get_agent_service", return_value=agent_svc),
        patch("backend.graph.nodes.get_paper_warning_service", return_value=warning_service),
    ):
        out = await nodes.extract_node(post_classify_state)

    warning_service.record.assert_awaited_once_with(
        post_classify_state["paper_id"],
        WarningType.EXTRACT,
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
        with (
            patch(
                "backend.graph.nodes.get_pipeline_completion_service",
                return_value=completion_svc,
            ),
            patch(
                "backend.services.rag_index_service.RagIndexService.index_paper_for_rag_async",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            out = await nodes.store_node(post_extract_state)
            # Drain while the RAG index patch is still active — the handler runs
            # asynchronously after publish and must see the same mock.
            await drain_event_bus()

    store_cls.return_value.save.assert_called_once()
    assert out["status"] == PaperStatus.INDEXING

    paper = await get_paper_service().get_paper(paper_id)
    assert paper.status == PaperStatus.READY


async def test_store_node_triggers_rag_indexing_after_finalize(
    post_extract_state: WorkflowState,
) -> None:
    with (
        patch("backend.services.graph_persistence_service.GraphStore") as store_cls,
        patch(
            "backend.services.rag_index_service.RagIndexService.index_paper_for_rag_async",
            new_callable=AsyncMock,
        ) as mock_rag_index,
    ):
        store_cls.return_value.save = MagicMock()
        persistence = GraphPersistenceService(store=store_cls.return_value)
        completion_svc = PipelineCompletionService(graph_persistence=persistence)
        with patch(
            "backend.graph.nodes.get_pipeline_completion_service",
            return_value=completion_svc,
        ):
            await nodes.store_node(post_extract_state)
        await drain_event_bus()
        mock_rag_index.assert_awaited_once()
        call_kwargs = mock_rag_index.await_args.kwargs
        assert call_kwargs["full_text"] == post_extract_state["full_text"]
        assert call_kwargs["graph"].paper_id == post_extract_state["paper_id"]


async def test_store_node_finalize_error_fails(
    post_extract_state: WorkflowState,
) -> None:
    completion_svc = MagicMock()
    completion_svc.finalize = AsyncMock(
        side_effect=ServiceError("PIPELINE_FAILED", "建图收尾失败: bad graph"),
    )
    with patch("backend.graph.nodes.get_pipeline_completion_service", return_value=completion_svc):
        out = await nodes.store_node(post_extract_state)

    assert out["failed"] is True
    assert "建图收尾失败" in out["error_message"]


async def test_store_node_rag_index_failure_does_not_block_ready(
    post_extract_state: WorkflowState,
) -> None:
    """RAG indexing failures must not leave the paper stuck in ``indexing``."""

    paper_id = post_extract_state["paper_id"]
    with (
        patch("backend.services.graph_persistence_service.GraphStore") as store_cls,
        patch(
            "backend.services.rag_index_service.RagIndexService.index_paper_for_rag_async",
            side_effect=RuntimeError("RAG crashed"),
        ),
    ):
        store_cls.return_value.save = MagicMock()
        persistence = GraphPersistenceService(store=store_cls.return_value)
        completion_svc = PipelineCompletionService(graph_persistence=persistence)
        with patch(
            "backend.graph.nodes.get_pipeline_completion_service",
            return_value=completion_svc,
        ):
            out = await nodes.store_node(post_extract_state)
        assert out["status"] == PaperStatus.INDEXING
        await drain_event_bus()
    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.READY_WITH_WARNINGS


async def test_store_node_rag_index_failure_records_extract_warning(
    post_extract_state: WorkflowState,
) -> None:
    """RAG indexing failures must surface as extract_warnings for operators."""

    from backend.rag.handlers import RAG_INDEX_WARNING_CODE

    paper_id = post_extract_state["paper_id"]
    with (
        patch("backend.services.graph_persistence_service.GraphStore") as store_cls,
        patch(
            "backend.services.rag_index_service.RagIndexService.index_paper_for_rag_async",
            new_callable=AsyncMock,
        ) as mock_rag_async,
    ):
        store_cls.return_value.save = MagicMock()
        persistence = GraphPersistenceService(store=store_cls.return_value)
        completion_svc = PipelineCompletionService(graph_persistence=persistence)

        async def failing_rag_async(*_args: Any, **kwargs: Any) -> None:
            from backend.repositories.pipeline_repository import PipelineRepository

            paper_id = kwargs.get("paper_id") or _args[0]
            await PipelineRepository().record_warnings(paper_id, extract=[RAG_INDEX_WARNING_CODE])
            raise RuntimeError("RAG crashed")

        mock_rag_async.side_effect = failing_rag_async
        with patch(
            "backend.graph.nodes.get_pipeline_completion_service",
            return_value=completion_svc,
        ):
            await nodes.store_node(post_extract_state)
        await drain_event_bus()
    paper = await get_paper_service().get_paper(paper_id)
    assert RAG_INDEX_WARNING_CODE in paper.extract_warnings


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
