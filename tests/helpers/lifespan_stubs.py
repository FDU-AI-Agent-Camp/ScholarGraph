# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Stub RAG wiring so FastAPI lifespan tests never open the default Chroma path."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest


def stub_lifespan_rag_wiring(monkeypatch: pytest.MonkeyPatch) -> None:
    """No-op HybridRetriever + VectorStore bind/reset; fake VectorStore constructor.

    Lifespan otherwise constructs ``VectorStore(paper_service=...)`` without an
    isolated ``chroma_path``, which is forbidden under pytest.
    """

    def _fake_vector_store(*_args: Any, **_kwargs: Any) -> MagicMock:
        return MagicMock(name="lifespan-stub-vector-store")

    monkeypatch.setattr(
        "backend.rag.hybrid_retriever.create_hybrid_retriever",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr("backend.rag.hybrid_retriever.bind_hybrid_retriever", lambda _r: None)
    monkeypatch.setattr("backend.rag.hybrid_retriever.reset_hybrid_retriever", lambda: None)
    monkeypatch.setattr("backend.rag.vector_store.VectorStore", _fake_vector_store)
    monkeypatch.setattr("backend.rag.vector_store_wiring.bind_vector_store", lambda _s: None)
    monkeypatch.setattr("backend.rag.vector_store_wiring.reset_vector_store", lambda: None)
