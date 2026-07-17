# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""B11 regression: cold import of LlmClient must not hit rag↔graph↔llm cycle."""

from __future__ import annotations

import importlib
import sys


def test_b11_cold_import_llm_client() -> None:
    for name in (
        "backend.llm.client",
        "backend.llm.mock_chat",
        "backend.rag.qa_router",
        "backend.rag",
        "backend.graph",
    ):
        sys.modules.pop(name, None)

    from backend.llm.client import LlmClient

    assert LlmClient is not None


def test_b11_rag_hybrid_retriever_lazy_export() -> None:
    from backend.rag import HybridRetriever, get_hybrid_retriever

    assert HybridRetriever is not None
    assert callable(get_hybrid_retriever)


def test_b11_graph_qa_stream_lazy_export() -> None:
    from backend.graph import QaEvent, qa_stream

    assert QaEvent is not None
    assert callable(qa_stream)


def test_b11_eval_collection_imports_llm_client_first() -> None:
    """Mirror pytest tests/eval/ ordering: llm.client before benchmark scripts."""
    for name in (
        "scripts.benchmark_qa",
        "backend.llm.client",
        "backend.rag.qa_router",
        "backend.rag",
        "backend.graph",
    ):
        sys.modules.pop(name, None)

    importlib.import_module("backend.llm.client")
    importlib.import_module("scripts.benchmark_qa")
