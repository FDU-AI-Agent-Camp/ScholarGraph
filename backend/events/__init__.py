# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Event bus exports."""

from backend.events.bus import EventBus, get_event_bus, on_event, reset_event_bus_cache, stop_event_bus_worker
from backend.events.pipeline_finalized_handlers import (
    register_pipeline_finalized_handlers,
    unregister_pipeline_finalized_handlers,
)
from backend.events.types import EventType, PipelineFinalized, RagIndexed

# Do not auto-register here: ``backend.rag.handlers`` imports ``events.bus``, which
# loads this package. Eager registration would re-enter ``rag.handlers`` mid-import.
# Registration is performed by ``reset_event_bus_cache``, FastAPI lifespan, and
# ``ensure_pipeline_finalized_handlers_registered`` on first ``get_event_bus`` use.


def __getattr__(name: str) -> object:
    if name == "pipeline_finalized_rag_handler":
        from backend.events.pipeline_finalized_handlers import pipeline_finalized_rag_handler

        return pipeline_finalized_rag_handler
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


__all__ = [
    "EventBus",
    "EventType",
    "PipelineFinalized",
    "RagIndexed",
    "get_event_bus",
    "on_event",
    "pipeline_finalized_rag_handler",
    "register_pipeline_finalized_handlers",
    "reset_event_bus_cache",
    "stop_event_bus_worker",
    "unregister_pipeline_finalized_handlers",
]
