"""RAG vector indexing primitives for ScholarGraph V2."""

from backend.rag.chunking import chunk_text
from backend.rag.indexing import graph_to_entities, graph_to_relations
from backend.rag.models import (
    EmbeddingClientProtocol,
    PaperChunk,
    PaperEntity,
    PaperRelation,
    VectorEvidenceType,
    VectorSearchResult,
)

__all__ = [
    "EmbeddingClientProtocol",
    "PaperChunk",
    "PaperEntity",
    "PaperRelation",
    "VectorEvidenceType",
    "VectorSearchResult",
    "chunk_text",
    "graph_to_entities",
    "graph_to_relations",
]
