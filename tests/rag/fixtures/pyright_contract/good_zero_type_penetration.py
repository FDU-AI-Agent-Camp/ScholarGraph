"""Pyright should pass: Retrieved* fields are inferred without cast/as_dict."""

from __future__ import annotations

from backend.rag.protocols import VectorStoreProtocol


async def access_retrieved_fields(store: VectorStoreProtocol) -> tuple[str, str, str]:
    chunks = await store.query_chunks("ImageNet top-1 accuracy", paper_id="stem-001")
    entities = await store.query_entities("ResNet-Light", paper_id="stem-001")
    relations = await store.query_relations("trained on", paper_id="stem-001")

    chunk_text = chunks[0].text if chunks else ""
    entity_label = entities[0].label if entities else ""
    relation_type = relations[0].relation_type if relations else ""
    return chunk_text, entity_label, relation_type
