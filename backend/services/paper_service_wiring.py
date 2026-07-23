# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Process-wide PaperService bind / get / reset (composition root).

Aligned with ``vector_store_wiring`` / ``hybrid_retriever`` wiring:

- **App lifespan** creates one instance, ``bind_paper_service``, exposes ``app.state``.
- **FastAPI deps** prefer ``app.state.paper_service``, fall back to ``get_paper_service``.
- **Workers / handlers** accept an optional injected ``paper_service``; only the
  composition root (or tests) should call ``get_paper_service()`` for the default.
- **Tests** call ``reset_paper_service()`` (or legacy ``get_paper_service.cache_clear()``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.services.paper_service import PaperService

__all__ = [
    "bind_paper_service",
    "get_paper_service",
    "reset_paper_service",
]

_global_paper_service: PaperService | None = None


def get_paper_service() -> PaperService:
    """Return the process-wide PaperService, creating a default instance if unbound."""
    global _global_paper_service
    if _global_paper_service is None:
        from backend.services.paper_service import PaperService

        _global_paper_service = PaperService()
    return _global_paper_service


def bind_paper_service(service: PaperService) -> None:
    """Register the process-wide PaperService (app lifespan / test fixtures)."""
    global _global_paper_service
    _global_paper_service = service


def reset_paper_service() -> None:
    """Clear the process-wide PaperService singleton (teardown / test isolation)."""
    global _global_paper_service
    _global_paper_service = None


# Back-compat: many tests still call ``get_paper_service.cache_clear()`` (lru_cache era).
get_paper_service.cache_clear = reset_paper_service  # type: ignore[attr-defined]
