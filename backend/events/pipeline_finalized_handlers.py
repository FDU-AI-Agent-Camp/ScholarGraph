# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Compatibility facade for PipelineFinalized registration (P10).

The exclusive official subscriber lives in ``backend.rag.handlers``. This module
no longer contains temporary handlers — only registration aliases for lifespan /
tests. Imports of ``backend.rag.handlers`` are deferred to break the
``rag.handlers`` ↔ ``events`` package cycle.

Lazy symbols ``pipeline_finalized_rag_handler`` / ``on_pipeline_finalized_for_rag``
are available via ``__getattr__`` (not listed in ``__all__`` — avoids ruff F822).
"""

from __future__ import annotations

from typing import Any


def register_pipeline_finalized_handlers(*, force: bool = False) -> None:
    """Bind the official exclusive RAG subscriber on the process-wide bus."""
    from backend.rag.handlers import register_rag_pipeline_finalized_handler

    register_rag_pipeline_finalized_handler(force=force)


def unregister_pipeline_finalized_handlers() -> None:
    """Remove the official handler (tests that install custom subscribers only)."""
    from backend.rag.handlers import unregister_rag_pipeline_finalized_handler

    unregister_rag_pipeline_finalized_handler()


def __getattr__(name: str) -> Any:
    if name in {"pipeline_finalized_rag_handler", "on_pipeline_finalized_for_rag"}:
        from backend.rag.handlers import on_pipeline_finalized_for_rag

        return on_pipeline_finalized_for_rag
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


__all__ = [
    "register_pipeline_finalized_handlers",
    "unregister_pipeline_finalized_handlers",
]
