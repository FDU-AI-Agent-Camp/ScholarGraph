"""Pyright should pass: optional top_k may be omitted or passed explicitly."""

from __future__ import annotations

from backend.rag.protocols import VectorStoreProtocol


async def implicit_top_k(store: VectorStoreProtocol) -> None:
    await store.query_chunks("accuracy", paper_id="stem-001")
    await store.query_entities("accuracy", paper_id="stem-001")
    await store.query_relations("accuracy", paper_id="stem-001")


async def explicit_top_k(store: VectorStoreProtocol) -> None:
    await store.query_chunks("accuracy", paper_id="stem-001", top_k=5)
    await store.query_entities("accuracy", paper_id="stem-001", top_k=3)
    await store.query_relations("accuracy", paper_id="stem-001", top_k=None)
