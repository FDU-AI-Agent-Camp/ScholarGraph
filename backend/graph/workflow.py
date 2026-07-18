# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""LangGraph StateGraph: ingest → wait_head_refine → classify → extract → store."""

import asyncio
from functools import lru_cache
from pathlib import Path
from typing import Literal, cast

from langgraph.graph import END, START, StateGraph

from backend.graph import nodes
from backend.graph.state import (
    NODE_CLASSIFY,
    NODE_EXTRACT,
    NODE_FAIL,
    NODE_INGEST,
    NODE_STORE,
    NODE_WAIT_HEAD_REFINE,
    PIPELINE_ORDER,
    WorkflowState,
    initial_workflow_state,
)
from backend.services.errors import PIPELINE_FAILED_CODE
from backend.services.paper_service import get_paper_service
from backend.services.pipeline_status_service import get_pipeline_status_service

RouteKey = Literal["continue", "fail", "background"]


def _route_after_step(state: WorkflowState) -> RouteKey:
    if state.get("failed"):
        return "fail"
    return "continue"


def _route_after_extract(state: WorkflowState) -> RouteKey:
    """Long papers schedule full extraction in the background; end the main pipeline.

    The background task will finalize and mark the paper ready/failed later.
    """
    if state.get("failed"):
        return "fail"
    if state.get("background_extraction_scheduled"):
        return "background"
    return "continue"


def build_paper_pipeline_graph() -> StateGraph:
    """Construct the single-paper pipeline graph (compile with `.compile()`)."""
    graph: StateGraph = StateGraph(WorkflowState)

    graph.add_node(NODE_INGEST, nodes.ingest_node)
    graph.add_node(NODE_WAIT_HEAD_REFINE, nodes.wait_head_refine_node)
    graph.add_node(NODE_CLASSIFY, nodes.classify_node)
    graph.add_node(NODE_EXTRACT, nodes.extract_node)
    graph.add_node(NODE_STORE, nodes.store_node)
    graph.add_node(NODE_FAIL, nodes.fail_node)

    graph.add_edge(START, NODE_INGEST)

    graph.add_conditional_edges(
        NODE_INGEST,
        _route_after_step,
        {"continue": NODE_WAIT_HEAD_REFINE, "fail": NODE_FAIL},
    )
    graph.add_conditional_edges(
        NODE_WAIT_HEAD_REFINE,
        _route_after_step,
        {"continue": NODE_CLASSIFY, "fail": NODE_FAIL},
    )
    graph.add_conditional_edges(
        NODE_CLASSIFY,
        _route_after_step,
        {"continue": NODE_EXTRACT, "fail": NODE_FAIL},
    )
    graph.add_conditional_edges(
        NODE_EXTRACT,
        _route_after_extract,
        {"continue": NODE_STORE, "fail": NODE_FAIL, "background": END},
    )
    graph.add_conditional_edges(
        NODE_STORE,
        _route_after_step,
        {"continue": END, "fail": NODE_FAIL},
    )
    graph.add_edge(NODE_FAIL, END)

    return graph


@lru_cache
def get_compiled_paper_pipeline():
    return build_paper_pipeline_graph().compile()


def pipeline_node_names() -> tuple[str, ...]:
    """Ordered business nodes (excludes START/END/fail)."""
    return PIPELINE_ORDER


async def run_paper_pipeline(paper_id: str, pdf_path: Path) -> WorkflowState:
    """
    Run the full single-paper pipeline asynchronously.

    Registers progress on ``GET /papers/{id}/status`` (including ``failed`` +
    ``error_code`` / ``failed_during`` when the graph routes to ``fail``).

    Args:
        paper_id: Existing paper identifier (must be registered in PaperService).
        pdf_path: Local path to the PDF file.

    Returns:
        Final LangGraph workflow state (``failed=True`` includes ``error_code``).

    Raises:
        FileNotFoundError: PDF path does not exist.
        ApiError: Paper not registered (from ``ensure_paper_exists``).
    """
    pdf_path = pdf_path.resolve()
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    paper_service = get_paper_service()
    await paper_service.ensure_paper_exists(paper_id)
    get_pipeline_status_service().start_processing(paper_id)
    from backend.services.paper_pipeline_ops import get_paper_pipeline_ops_service

    pipeline_generation_id = get_paper_pipeline_ops_service().begin_pipeline_generation(paper_id)

    initial = initial_workflow_state(
        paper_id=paper_id,
        pdf_path=str(pdf_path),
        pipeline_generation_id=pipeline_generation_id,
    )
    final_state: WorkflowState = cast(
        WorkflowState,
        await get_compiled_paper_pipeline().ainvoke(initial),
    )

    if final_state.get("failed"):
        await _ensure_failed_status_persisted(paper_id, final_state)
        return final_state

    # store_node leaves papers in ``indexing``; wait for official RAG handler to promote.
    # Drain on the async-bridge loop (same loop publish_sync uses). Awaiting
    # EventBus.drain() on the caller loop can cross-loop-deadlock the Queue.
    from backend.events.bus import get_event_bus
    from backend.graph.state import STAGE_PERCENT
    from backend.schemas.paper import PaperStatus, PipelineStage

    await asyncio.to_thread(get_event_bus().drain_sync)
    snapshot = await paper_service.get_status(paper_id)
    if snapshot.status in {PaperStatus.READY, PaperStatus.READY_WITH_WARNINGS}:
        promoted = cast(WorkflowState, dict(final_state))
        promoted["status"] = snapshot.status
        promoted["stage"] = PipelineStage.READY
        promoted["percent"] = STAGE_PERCENT[PipelineStage.READY]
        promoted["message"] = snapshot.message or "建图完成"
        promoted["failed"] = False
        return promoted
    return final_state


async def _ensure_failed_status_persisted(paper_id: str, final_state: WorkflowState) -> None:
    """Idempotent guard: fail_node 应已写入；若缺失则补写 failed 快照。"""
    snapshot = await get_paper_service().get_status(paper_id)
    from backend.schemas.paper import PaperStatus

    if snapshot.status == PaperStatus.FAILED and snapshot.error_code:
        return

    from backend.schemas.paper import PipelineStage

    failed_during = final_state.get("failed_during") or final_state.get("stage")
    failed_stage = failed_during if isinstance(failed_during, PipelineStage) else None
    if failed_stage == PipelineStage.FAILED:
        failed_stage = None

    get_paper_service().fail_pipeline(
        paper_id,
        message=final_state.get("error_message") or final_state.get("message") or "流水线失败",
        error_code=final_state.get("error_code", PIPELINE_FAILED_CODE),
        failed_during=failed_stage,
    )
