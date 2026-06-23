"""LangGraph sub-graph for two-phase extraction with self-repair (v2)."""

from __future__ import annotations

import logging
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from backend.agents.extract_heuristic import extract_title
from backend.agents.extract_types import ExtractResult
from backend.config import get_settings
from backend.graph.head_store import HeadStore
from backend.schemas.graph import GraphEdge, GraphNode, NodeType, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm

logger = logging.getLogger(__name__)

RouteKey = Literal["success", "retry_nodes", "retry_edges", "fallback"]
RepairLevel = Literal["nodes", "edges"]
StartRouteKey = Literal["mock", "live"]


class ExtractSubgraphState(TypedDict, total=False):
    """State carried through the extraction sub-graph.

    Includes a subset of outer ``WorkflowState`` keys (failed, error_code,
    error_message, status, stage, percent, message) so that unrecoverable
    failures propagate to the parent graph.
    """

    paper_id: str
    full_text: str
    paradigm: str
    title: str | None
    head_context: str | None

    nodes: Any  # ExtractedNodeList
    edges: Any  # ExtractedEdgeList

    repair_attempts: int
    last_error: str | None
    error_level: RepairLevel | None

    graph: dict[str, Any] | None
    extract_warnings: list[str]

    # Failure propagation to outer workflow
    failed: bool
    error_code: str
    error_message: str
    status: Any
    stage: Any
    percent: int
    message: str


def _resolve_head_context(paper_id: str) -> str | None:
    """Load refined head text from HeadStore if available."""
    record = HeadStore().load(paper_id)
    if record is None:
        return None
    head = record.merged
    parts = [head.title.strip(), head.abstract.strip(), head.intro.strip()]
    merged = "\n\n".join(part for part in parts if part)
    return merged or None


def _resolve_title(full_text: str, title: str | None) -> str:
    if title and title.strip():
        return title.strip()
    return extract_title(full_text)


def _subgraph_failure_patch(error_code: str, error_message: str) -> ExtractSubgraphState:
    """Return state patch that signals failure to the outer workflow."""
    from backend.graph.state import STAGE_PERCENT
    from backend.schemas.paper import PaperStatus, PipelineStage

    return {
        "failed": True,
        "error_code": error_code,
        "error_message": error_message,
        "status": PaperStatus.PROCESSING,
        "stage": PipelineStage.EXTRACTING,
        "percent": STAGE_PERCENT[PipelineStage.EXTRACTING],
        "message": error_message,
    }


def _route_check_failed(state: ExtractSubgraphState) -> Literal["continue", "fail"]:
    """Skip downstream nodes when a prior node already failed."""
    return "fail" if state.get("failed") else "continue"


async def extract_nodes_node(state: ExtractSubgraphState) -> ExtractSubgraphState:
    """Stage 1: extract nodes from the paper text."""
    from backend.agents.extract_nodes import extract_nodes_with_llm
    from backend.services.errors import ServiceError

    paper_id = state["paper_id"]
    full_text = state["full_text"]
    paradigm = Paradigm(state["paradigm"])
    title = _resolve_title(full_text, state.get("title"))
    head_context = state.get("head_context") or _resolve_head_context(paper_id)

    previous_error = None
    if state.get("error_level") == "nodes" and state.get("last_error"):
        previous_error = state["last_error"]

    try:
        node_list = await extract_nodes_with_llm(
            full_text,
            paradigm,
            paper_id=paper_id,
            title=title,
            head_context=head_context,
            previous_error=previous_error,
        )
    except ServiceError as exc:
        return _subgraph_failure_patch(exc.code, exc.message)
    except Exception as exc:
        logger.exception("extract_nodes_node failed for %s", paper_id)
        return _subgraph_failure_patch("PIPELINE_FAILED", f"节点抽取失败: {exc}")

    patch: ExtractSubgraphState = {
        "nodes": node_list,
        "title": title,
        "head_context": head_context,
    }
    if previous_error is None:
        patch["repair_attempts"] = 0
    return patch


async def build_edges_node(state: ExtractSubgraphState) -> ExtractSubgraphState:
    """Stage 2: build edges from extracted nodes."""
    from backend.agents.extract_edges import build_edges_with_llm
    from backend.services.errors import ServiceError

    nodes = state["nodes"]
    full_text = state["full_text"]
    paper_id = state["paper_id"]
    title = state.get("title")
    head_context = state.get("head_context")

    previous_error = None
    if state.get("error_level") == "edges" and state.get("last_error"):
        previous_error = state["last_error"]

    try:
        edge_list = await build_edges_with_llm(
            nodes,
            full_text,
            paper_id=paper_id,
            title=title,
            head_context=head_context,
            previous_error=previous_error,
        )
    except ServiceError as exc:
        return _subgraph_failure_patch(exc.code, exc.message)
    except Exception as exc:
        logger.exception("build_edges_node failed for %s", paper_id)
        return _subgraph_failure_patch("PIPELINE_FAILED", f"关系抽取失败: {exc}")

    return {"edges": edge_list}


def validate_node(state: ExtractSubgraphState) -> ExtractSubgraphState:
    """Validate combined nodes + edges; on failure prepare repair context."""
    from backend.agents.extract_repair import (
        build_extracted_graph,
        classify_validation_error,
        format_error_messages,
    )

    nodes = state["nodes"]
    edges = state["edges"]
    paper_id = state["paper_id"]
    paradigm = Paradigm(state["paradigm"])
    title = state.get("title")

    summary = f"Two-phase extraction ({paradigm.value}): {len(nodes.nodes)} nodes, {len(edges.edges)} edges."

    try:
        extracted_graph = build_extracted_graph(
            paper_id=paper_id,
            title=title,
            paradigm=paradigm,
            nodes=nodes,
            edges=edges,
            summary=summary,
        )
    except ValidationError as exc:
        repair_attempts = state.get("repair_attempts", 0) + 1
        error_level = classify_validation_error(exc)
        logger.warning(
            "extract_validation_failed",
            extra={
                "paper_id": paper_id,
                "paradigm": paradigm.value,
                "repair_attempts": repair_attempts,
                "error_level": error_level,
            },
        )
        return {
            "repair_attempts": repair_attempts,
            "last_error": format_error_messages(exc),
            "error_level": error_level,
        }

    unified = UnifiedPaperGraph(
        paper_id=paper_id,
        title=title,
        paradigm=paradigm,
        nodes=[GraphNode(id=n.id, label=n.label, type=NodeType(n.type), data=n.data) for n in extracted_graph.nodes],
        edges=[
            GraphEdge(
                id=e.id,
                source=e.source,
                target=e.target,
                label=e.label,
                type=e.type,
                rationale=e.rationale,
                source_span=e.source_span,
                confidence=e.confidence,
                data=e.data,
            )
            for e in extracted_graph.edges
        ],
        summary=summary,
    )

    parse_warnings = list(dict.fromkeys(nodes.warnings + edges.warnings))
    return {
        "graph": unified.model_dump(mode="json"),
        "extract_warnings": parse_warnings,
        "last_error": None,
        "error_level": None,
    }


def _route_after_validate(state: ExtractSubgraphState) -> RouteKey:
    if state.get("graph") is not None:
        return "success"

    max_retries = get_settings().extract_repair_max_retries
    if state.get("repair_attempts", 0) > max_retries:
        logger.warning(
            "extract_repair_exhausted",
            extra={
                "paper_id": state["paper_id"],
                "paradigm": state["paradigm"],
                "max_retries": max_retries,
            },
        )
        return "fallback"

    error_level = state.get("error_level", "edges")
    if error_level == "nodes":
        return "retry_nodes"
    return "retry_edges"


async def fallback_to_heuristic_node(state: ExtractSubgraphState) -> ExtractSubgraphState:
    """Final safety net: return a heuristic graph when repair is exhausted."""
    from backend.agents.extract_heuristic import build_heuristic_graph

    full_text = state["full_text"]
    paradigm = Paradigm(state["paradigm"])
    title = state.get("title")

    graph = build_heuristic_graph(full_text, paradigm, title=title)
    logger.warning(
        "extract_fallback_to_heuristic",
        extra={"paper_id": state["paper_id"], "paradigm": paradigm.value},
    )
    return {
        "graph": graph.model_dump(mode="json"),
        "extract_warnings": ["extract_heuristic_fallback"],
        "last_error": None,
        "error_level": None,
    }


async def mock_extract_node(state: ExtractSubgraphState) -> ExtractSubgraphState:
    """Mock path: return the deterministic fixture graph directly.

    This node is only reachable when the sub-graph is invoked while
    ``LLM_MODE=mock``; the main pipeline mock path instead goes through
    ``AgentService.extract_graph`` → ``extract()`` directly.
    """
    from backend.agents.mock_agents import mock_extract
    from backend.services.errors import ServiceError

    paper_id = state["paper_id"]
    full_text = state["full_text"]
    paradigm = Paradigm(state["paradigm"])

    try:
        graph = mock_extract(full_text, paradigm)
        graph = graph.model_copy(update={"paper_id": paper_id, "paradigm": paradigm})
    except ServiceError as exc:
        return _subgraph_failure_patch(exc.code, exc.message)
    except Exception as exc:
        logger.exception("mock_extract_node failed for %s", paper_id)
        return _subgraph_failure_patch("PIPELINE_FAILED", f"Mock 抽取失败: {exc}")

    logger.info(
        "extract_mock_direct",
        extra={
            "paper_id": paper_id,
            "paradigm": paradigm.value,
        },
    )
    return {
        "graph": graph.model_dump(mode="json"),
        "extract_warnings": [],
        "last_error": None,
        "error_level": None,
    }


def _route_start(state: ExtractSubgraphState) -> StartRouteKey:
    """Route mock mode directly to fixture output; otherwise enter two-phase LLM path."""
    if get_settings().is_llm_mock:
        return "mock"
    return "live"


def build_extract_subgraph() -> StateGraph:
    """Construct the two-phase extraction sub-graph with self-repair."""
    graph: StateGraph = StateGraph(ExtractSubgraphState)

    graph.add_node("extract_nodes", extract_nodes_node)
    graph.add_node("build_edges", build_edges_node)
    graph.add_node("validate", validate_node)
    graph.add_node("fallback_to_heuristic", fallback_to_heuristic_node)
    graph.add_node("mock_extract", mock_extract_node)

    graph.add_conditional_edges(
        START,
        _route_start,
        {"mock": "mock_extract", "live": "extract_nodes"},
    )
    graph.add_conditional_edges(
        "mock_extract",
        _route_check_failed,
        {"continue": END, "fail": END},
    )
    graph.add_conditional_edges(
        "extract_nodes",
        _route_check_failed,
        {"continue": "build_edges", "fail": END},
    )
    graph.add_conditional_edges(
        "build_edges",
        _route_check_failed,
        {"continue": "validate", "fail": END},
    )
    graph.add_conditional_edges(
        "validate",
        _route_after_validate,
        {
            "success": END,
            "retry_nodes": "extract_nodes",
            "retry_edges": "build_edges",
            "fallback": "fallback_to_heuristic",
        },
    )
    graph.add_edge("fallback_to_heuristic", END)

    return graph


async def run_extract_subgraph(
    full_text: str,
    paradigm: Paradigm,
    *,
    paper_id: str,
    title: str | None = None,
    head_context: str | None = None,
) -> ExtractResult:
    """Run the extraction sub-graph standalone (used by extractor.py)."""
    subgraph = build_extract_subgraph().compile()
    initial_state: ExtractSubgraphState = {
        "paper_id": paper_id,
        "full_text": full_text,
        "paradigm": paradigm.value,
        "title": title,
        "head_context": head_context,
        "repair_attempts": 0,
        "extract_warnings": [],
    }
    final_state = await subgraph.ainvoke(initial_state)

    graph_data = final_state.get("graph")
    if graph_data is None:
        raise RuntimeError("Extract sub-graph finished without a graph")

    graph = UnifiedPaperGraph.model_validate(graph_data)
    return ExtractResult(graph=graph, warnings=final_state.get("extract_warnings", []))
