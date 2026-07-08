"""RAG vector indexing primitives for ScholarGraph V2."""

from backend.rag.chunking import chunk_text
from backend.rag.handlers import index_paper_for_rag
from backend.rag.hybrid_retriever import HybridRetriever
from backend.rag.indexing import graph_to_entities, graph_to_relations
from backend.rag.models import (
    EmbeddingClientProtocol,
    PaperChunk,
    PaperEntity,
    PaperRelation,
    QuestionScale,
    RetrievalContext,
    RetrievedChunk,
    RetrievedEntity,
    RetrievedRelation,
    VectorEvidenceType,
)
from backend.rag.qa_router import detect_question_scale
from backend.rag.vector_store import VectorStore

__all__ = [
    "EmbeddingClientProtocol",
    "HybridRetriever",
    "PaperChunk",
    "PaperEntity",
    "PaperRelation",
    "QuestionScale",
    "RetrievedChunk",
    "RetrievedEntity",
    "RetrievedRelation",
    "RetrievalContext",
    "VectorEvidenceType",
    "VectorStore",
    "chunk_text",
    "detect_question_scale",
    "graph_to_entities",
    "graph_to_relations",
    "index_paper_for_rag",
]
