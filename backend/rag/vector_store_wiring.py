# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Process-wide VectorStore bind / get / reset (aligned with HybridRetriever wiring)."""

from __future__ import annotations

import sys

from backend.rag.vector_store import VectorStore

__all__ = [
    "bind_vector_store",
    "get_vector_store",
    "reset_vector_store",
]

_global_vector_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    """Return the process-wide VectorStore, creating a default instance if unbound."""
    global _global_vector_store
    if _global_vector_store is None:
        if "pytest" in sys.modules:
            raise RuntimeError(
                "VectorStore singleton unbound under pytest; "
                "call bind_vector_store(...) from a fixture or inject the store explicitly. "
                "Lazy default construction is forbidden in tests to avoid Chroma path pollution.",
            )
        from backend.services.paper_service import get_paper_service

        _global_vector_store = VectorStore(paper_service=get_paper_service())
    return _global_vector_store


def bind_vector_store(store: VectorStore) -> None:
    """Register the process-wide VectorStore (app lifespan / test fixtures)."""
    global _global_vector_store
    _global_vector_store = store


def reset_vector_store() -> None:
    """Clear the process-wide VectorStore singleton (teardown / test isolation)."""
    global _global_vector_store
    _global_vector_store = None
