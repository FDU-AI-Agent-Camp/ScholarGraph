"""Contract validation for ``PipelineFinalized`` official RAG-handler intake."""

from __future__ import annotations

import logging

from pydantic import ValidationError

from backend.events.types import PipelineFinalized
from backend.repositories.paper_repository import get_paper_repository
from backend.schemas.graph import UnifiedPaperGraph

logger = logging.getLogger(__name__)


class PipelineFinalizedContractError(ValueError):
    """Raised when a ``PipelineFinalized`` payload fails schema or DB checks."""


def pipeline_finalized_correlation_id(paper_id: str) -> str:
    """Stable correlation key shared by publisher and subscriber logs."""
    return paper_id.strip()


async def validate_pipeline_finalized_payload(event: object) -> UnifiedPaperGraph:
    """Strong-type and topology checks before the temporary RAG handler runs."""
    if not isinstance(event, PipelineFinalized):
        msg = f"expected PipelineFinalized, got {type(event).__name__}"
        raise PipelineFinalizedContractError(msg)

    paper_id = event.paper_id.strip() if isinstance(event.paper_id, str) else ""
    if not paper_id:
        raise PipelineFinalizedContractError("paper_id must be a non-empty string")

    full_text = event.full_text if isinstance(event.full_text, str) else ""
    if not full_text.strip():
        raise PipelineFinalizedContractError(f"full_text must be non-empty for paper {paper_id}")

    if not isinstance(event.graph, UnifiedPaperGraph):
        msg = f"graph must be UnifiedPaperGraph, got {type(event.graph).__name__}"
        raise PipelineFinalizedContractError(msg)

    try:
        graph = UnifiedPaperGraph.model_validate(event.graph.model_dump(mode="json"))
    except ValidationError as exc:
        raise PipelineFinalizedContractError(f"graph failed schema validation for paper {paper_id}") from exc
    if graph.paper_id != paper_id:
        raise PipelineFinalizedContractError(
            f"graph.paper_id ({graph.paper_id!r}) does not match event.paper_id ({paper_id!r})",
        )

    if not graph.nodes:
        raise PipelineFinalizedContractError(f"graph must contain at least one node for paper {paper_id}")

    node_ids = {node.id for node in graph.nodes}
    if len(node_ids) != len(graph.nodes):
        raise PipelineFinalizedContractError(f"graph contains duplicate node ids for paper {paper_id}")

    for edge in graph.edges:
        if edge.source not in node_ids:
            raise PipelineFinalizedContractError(
                f"graph edge {edge.id!r} references missing source node {edge.source!r}",
            )
        if edge.target not in node_ids:
            raise PipelineFinalizedContractError(
                f"graph edge {edge.id!r} references missing target node {edge.target!r}",
            )

    correlation_id = pipeline_finalized_correlation_id(paper_id)
    logger.info(
        "pipeline_finalized_fetching_metadata",
        extra={
            "correlation_id": correlation_id,
            "paper_id": paper_id,
            "channel": "event_bus_subscriber",
        },
    )
    paper = await get_paper_repository().get(paper_id)
    if paper is None:
        raise PipelineFinalizedContractError(f"paper_id {paper_id!r} not found in database")

    return graph
