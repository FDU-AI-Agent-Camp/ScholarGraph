# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""FastAPI dependencies."""

from uuid import uuid4

from fastapi import Header, Request

from backend.config import Settings, get_settings
from backend.rag.hybrid_retriever import HybridRetriever, get_hybrid_retriever
from backend.services.paper_service import PaperService, get_paper_service


def get_request_id(x_request_id: str | None = Header(default=None, alias="X-Request-Id")) -> str:
    return x_request_id or str(uuid4())


def get_settings_dep() -> Settings:
    return get_settings()


def get_paper_service_dep(request: Request) -> PaperService:
    """Prefer the lifespan-bound instance; fall back to the process singleton."""
    state_service = getattr(request.app.state, "paper_service", None)
    if isinstance(state_service, PaperService):
        return state_service
    return get_paper_service()


def get_hybrid_retriever_dep(request: Request) -> HybridRetriever:
    """Reuse the HybridRetriever created at app startup (``app.state``)."""
    state_retriever = getattr(request.app.state, "hybrid_retriever", None)
    if state_retriever is not None:
        return state_retriever
    return get_hybrid_retriever()
