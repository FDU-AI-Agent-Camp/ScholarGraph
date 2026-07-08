"""Tests for the V2 hybrid graph + vector retriever."""

from __future__ import annotations

from typing import Any

import pytest
from backend.rag.hybrid_retriever import HybridRetriever
from backend.rag.models import (
    QuestionScale,
    RetrievedChunk,
    RetrievedEntity,
    RetrievedRelation,
)
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm


class FakeVectorStore:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def query_chunks(
        self,
        query_text: str,
        *,
        paper_id: str,
        top_k: int | None = None,
        query_embedding: list[float] | None = None,
    ) -> list[RetrievedChunk]:
        self.calls.append(_call("chunks", query_text, paper_id, top_k, query_embedding))
        return [
            RetrievedChunk(
                id="paper-1:chunk:0",
                paper_id=paper_id,
                text="Dataset Alpha reaches 0.89 F1.",
                chunk_id="paper-1:chunk:0",
                chunk_index=0,
                char_start=0,
                char_end=32,
                page_start=3,
                page_end=3,
            )
        ]

    async def query_entities(
        self,
        query_text: str,
        *,
        paper_id: str,
        top_k: int | None = None,
        query_embedding: list[float] | None = None,
    ) -> list[RetrievedEntity]:
        self.calls.append(_call("entities", query_text, paper_id, top_k, query_embedding))
        return [
            RetrievedEntity(
                id="paper-1:entity:n_dataset",
                paper_id=paper_id,
                text="Dataset Alpha",
                entity_id="n_dataset",
                label="Dataset Alpha",
                node_type="Dataset",
            )
        ]

    async def query_relations(
        self,
        query_text: str,
        *,
        paper_id: str,
        top_k: int | None = None,
        query_embedding: list[float] | None = None,
    ) -> list[RetrievedRelation]:
        self.calls.append(_call("relations", query_text, paper_id, top_k, query_embedding))
        return [
            RetrievedRelation(
                id="paper-1:relation:e_eval",
                paper_id=paper_id,
                text="Method evaluates Dataset Alpha",
                relation_id="e_eval",
                source_id="n_method",
                target_id="n_dataset",
                relation_type="EVALUATED_ON",
            )
        ]


def _call(
    collection: str,
    query_text: str,
    paper_id: str,
    top_k: int | None,
    query_embedding: list[float] | None,
) -> dict[str, Any]:
    return {
        "collection": collection,
        "query_text": query_text,
        "paper_id": paper_id,
        "top_k": top_k,
        "query_embedding": query_embedding,
    }


def _graph() -> UnifiedPaperGraph:
    return UnifiedPaperGraph(
        paper_id="paper-1",
        title="Hybrid RAG paper",
        paradigm=Paradigm.STEM,
        nodes=[
            GraphNode(id="n_question", label="How to improve QA?", type="ResearchQuestion"),
            GraphNode(id="n_method", label="Hybrid Retriever", type="Method"),
            GraphNode(id="n_dataset", label="Dataset Alpha", type="Dataset"),
            GraphNode(id="n_metric", label="F1", type="Metric"),
        ],
        edges=[
            GraphEdge(
                id="e_uses",
                source="n_question",
                target="n_method",
                label="USES_METHOD",
                type="USES_METHOD",
            ),
            GraphEdge(
                id="e_eval",
                source="n_method",
                target="n_dataset",
                label="EVALUATED_ON",
                type="EVALUATED_ON",
            ),
        ],
    )


@pytest.mark.asyncio
async def test_skeleton_scale_uses_only_graph_subgraph() -> None:
    vector_store = FakeVectorStore()
    retriever = HybridRetriever(vector_store=vector_store)

    context = await retriever.retrieve(
        "paper-1",
        "这篇论文做了什么？",
        _graph(),
        scale=QuestionScale.SKELETON,
    )

    assert context.scale == QuestionScale.SKELETON
    assert context.entities == []
    assert context.relations == []
    assert context.chunks == []
    assert vector_store.calls == []
    assert {node["id"] for node in context.nodes}


@pytest.mark.asyncio
async def test_detail_scale_queries_three_collections_and_merges_graph_context() -> None:
    vector_store = FakeVectorStore()
    retriever = HybridRetriever(vector_store=vector_store)

    context = await retriever.retrieve(
        "paper-1",
        "具体用了什么数据集？",
        _graph(),
        scale=QuestionScale.DETAIL,
    )

    assert {call["collection"] for call in vector_store.calls} == {"entities", "relations", "chunks"}
    assert all(call["paper_id"] == "paper-1" for call in vector_store.calls)
    assert [entity.entity_id for entity in context.entities] == ["n_dataset"]
    assert [relation.relation_id for relation in context.relations] == ["e_eval"]
    assert [chunk.chunk_id for chunk in context.chunks] == ["paper-1:chunk:0"]
    assert {"n_method", "n_dataset"}.issubset({node["id"] for node in context.nodes})
    assert "e_eval" in {edge["id"] for edge in context.edges}


@pytest.mark.asyncio
async def test_detail_scale_passes_query_transform_and_query_embedding() -> None:
    vector_store = FakeVectorStore()
    retriever = HybridRetriever(vector_store=vector_store)
    embedding = [0.1, 0.2, 0.3]

    await retriever.retrieve(
        "paper-1",
        "数据集是什么？",
        _graph(),
        scale=QuestionScale.DETAIL,
        query_transform=lambda question: f"hyde: {question}",
        query_embedding=embedding,
    )

    assert all(call["query_text"].startswith("hyde: ") for call in vector_store.calls)
    assert all(call["query_embedding"] == embedding for call in vector_store.calls)


@pytest.mark.asyncio
async def test_cross_paper_scale_is_rejected_for_single_paper_retrieval() -> None:
    retriever = HybridRetriever(vector_store=FakeVectorStore())

    with pytest.raises(ValueError, match="cross-paper"):
        await retriever.retrieve(
            "paper-1",
            "对比两篇论文",
            _graph(),
            scale=QuestionScale.CROSS_PAPER,
        )
