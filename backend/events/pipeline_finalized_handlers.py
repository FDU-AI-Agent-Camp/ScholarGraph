"""Built-in subscribers for ``PipelineFinalized`` (persistence-core).

The temporary RAG handler bridges finalize → vector indexing until
``feature/backend/rag-vector-store`` lands its production handler in
``backend/rag/handlers.py``. Remove this module's subscriber when that PR merges.
"""

from __future__ import annotations

import logging

from backend.events.bus import get_event_bus
from backend.events.pipeline_finalized_contract import (
    PipelineFinalizedContractError,
    pipeline_finalized_correlation_id,
    validate_pipeline_finalized_payload,
)
from backend.events.types import EventType, PipelineFinalized

logger = logging.getLogger(__name__)

_TEMPORARY_HANDLER_REGISTERED = False


async def temporary_pipeline_finalized_rag_handler(event: PipelineFinalized) -> None:
    """Consume finalize events: audit contract, log, delegate to RAG indexing."""
    correlation_id = pipeline_finalized_correlation_id(event.paper_id)
    logger.info(
        "pipeline_finalized_consumed",
        extra={
            "correlation_id": correlation_id,
            "paper_id": event.paper_id,
            "event_type": EventType.PIPELINE_FINALIZED.value,
            "channel": "event_bus_subscriber",
        },
    )

    try:
        graph = await validate_pipeline_finalized_payload(event)
    except PipelineFinalizedContractError:
        logger.exception(
            "pipeline_finalized_contract_rejected",
            extra={
                "correlation_id": correlation_id,
                "paper_id": event.paper_id,
                "event_type": EventType.PIPELINE_FINALIZED.value,
            },
        )
        raise

    logger.info(
        "pipeline_finalized_contract_ok",
        extra={
            "correlation_id": correlation_id,
            "paper_id": event.paper_id,
            "full_text_chars": len(event.full_text),
            "graph_node_count": len(graph.nodes),
            "graph_edge_count": len(graph.edges),
        },
    )

    from backend.services.rag_index_service import get_rag_index_service

    await get_rag_index_service().index_paper_for_rag_async(
        event.paper_id,
        full_text=event.full_text,
        graph=graph,
    )


def register_pipeline_finalized_handlers(*, force: bool = False) -> None:
    """Bind built-in ``PipelineFinalized`` subscribers on the process-wide bus."""
    global _TEMPORARY_HANDLER_REGISTERED

    bus = get_event_bus()
    handlers = bus._handlers[EventType.PIPELINE_FINALIZED]
    if temporary_pipeline_finalized_rag_handler in handlers:
        if not force:
            return
        handlers.remove(temporary_pipeline_finalized_rag_handler)

    bus.subscribe(EventType.PIPELINE_FINALIZED, temporary_pipeline_finalized_rag_handler)
    _TEMPORARY_HANDLER_REGISTERED = True


def unregister_pipeline_finalized_handlers() -> None:
    """Remove built-in handlers (tests that install custom subscribers only)."""
    global _TEMPORARY_HANDLER_REGISTERED

    bus = get_event_bus()
    handlers = bus._handlers[EventType.PIPELINE_FINALIZED]
    if temporary_pipeline_finalized_rag_handler in handlers:
        handlers.remove(temporary_pipeline_finalized_rag_handler)
    _TEMPORARY_HANDLER_REGISTERED = False
