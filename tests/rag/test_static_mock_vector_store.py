# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Tests for file-backed StaticMockVectorStore used in mock-mode benchmark runs."""

from __future__ import annotations

import pytest
from backend.graph.qa_samples import STEM_DEMO_PAPER_ID, load_stem_demo_graph
from backend.rag.hybrid_retriever import HybridRetriever
from backend.rag.models import QuestionScale
from backend.rag.static_mock_vector_store import StaticMockVectorStore

from tests.conftest import REPO_ROOT


@pytest.mark.asyncio
async def test_static_mock_vector_store_returns_stem_chunks() -> None:
    store = StaticMockVectorStore.load(REPO_ROOT / "data" / "mock_vector_store.json")
    assert await store.exists(STEM_DEMO_PAPER_ID) is True
    chunks = await store.query_chunks(
        "ResNet-Light top-1 accuracy ImageNet learning rate",
        paper_id=STEM_DEMO_PAPER_ID,
        top_k=2,
    )
    assert len(chunks) == 2
    assert all(chunk.chunk_id.startswith("stem-001:chunk:") for chunk in chunks)
    assert "78.5%" in chunks[0].text or "78.5%" in chunks[1].text


@pytest.mark.asyncio
async def test_hybrid_retriever_uses_static_mock_vectors_for_stem_detail() -> None:
    store = StaticMockVectorStore.load_default()
    retriever = HybridRetriever(vector_store=store)
    graph = load_stem_demo_graph()

    context = await retriever.retrieve(
        STEM_DEMO_PAPER_ID,
        "What is the top-1 accuracy of ResNet-Light on ImageNet?",
        graph,
        scale=QuestionScale.DETAIL,
    )

    assert context.scale == QuestionScale.DETAIL
    assert context.nodes
    assert len(context.chunks) >= 1
    assert context.chunks[0].chunk_id == "stem-001:chunk:42" or any(
        "ImageNet" in chunk.text for chunk in context.chunks
    )
