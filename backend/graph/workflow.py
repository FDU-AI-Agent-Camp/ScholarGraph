"""LangGraph StateGraph: ingest → classify → extract → store."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from langgraph.graph import END, START, StateGraph

from backend.graph import nodes
from backend.graph.state import (
    NODE_CLASSIFY,
    NODE_EXTRACT,
    NODE_FAIL,
    NODE_INGEST,
    NODE_STORE,
    PIPELINE_ORDER,
    WorkflowState,
    initial_workflow_state,
)
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.services.paper_service import get_paper_service
from backend.services.pipeline_status_service import get_pipeline_status_service

RouteKey = Literal["continue", "fail"]


def _route_after_step(state: WorkflowState) -> RouteKey:
    if state.get("failed"):
        return "fail"
    return "continue"


def build_paper_pipeline_graph() -> StateGraph:
    """Construct the single-paper pipeline graph (compile with `.compile()`)."""
    graph: StateGraph = StateGraph(WorkflowState)

    graph.add_node(NODE_INGEST, nodes.ingest_node)
    graph.add_node(NODE_CLASSIFY, nodes.classify_node)
    graph.add_node(NODE_EXTRACT, nodes.extract_node)
    graph.add_node(NODE_STORE, nodes.store_node)
    graph.add_node(NODE_FAIL, nodes.fail_node)

    graph.add_edge(START, NODE_INGEST)

    graph.add_conditional_edges(
        NODE_INGEST,
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
        _route_after_step,
        {"continue": NODE_STORE, "fail": NODE_FAIL},
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

    Updates progress via PaperService for GET /papers/{id}/status polling.
    """
    pdf_path = pdf_path.resolve()
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    get_paper_service().ensure_paper_exists(paper_id)
    get_pipeline_status_service().start_processing(paper_id)

    initial = initial_workflow_state(paper_id=paper_id, pdf_path=str(pdf_path))
    final_state: WorkflowState = await get_compiled_paper_pipeline().ainvoke(initial)
    return final_state
