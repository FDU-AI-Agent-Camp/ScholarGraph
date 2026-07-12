"""RAG vector indexing primitives for ScholarGraph V2."""

from backend.rag.chunking import chunk_text
from backend.rag.handlers import index_paper_for_rag
from backend.rag.indexing import graph_to_entities, graph_to_relations
from backend.rag.models import (
    EmbeddingClientProtocol,
    JudgeMicroOutput,
    JudgeSchema,
    PaperChunk,
    PaperEntity,
    PaperRelation,
    QAJudgeResult,
    QuestionScale,
    RetrievalContext,
    RetrievedChunk,
    RetrievedEntity,
    RetrievedRelation,
    SentenceJudgment,
    SentenceLabel,
    TrackBJudgeSchema,
    VectorEvidenceType,
)
from backend.rag.vector_store import VectorStore

_HYBRID_RETRIEVER_EXPORTS = frozenset(
    {
        "HybridRetriever",
        "bind_hybrid_retriever",
        "create_hybrid_retriever",
        "get_hybrid_retriever",
        "reset_hybrid_retriever",
    }
)


def __getattr__(name: str) -> object:
    """Defer hybrid_retriever import — it pulls graph.query during llm.client init."""
    if name not in _HYBRID_RETRIEVER_EXPORTS:
        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg)
    from backend.rag.hybrid_retriever import (
        HybridRetriever,
        bind_hybrid_retriever,
        create_hybrid_retriever,
        get_hybrid_retriever,
        reset_hybrid_retriever,
    )

    mapping = {
        "HybridRetriever": HybridRetriever,
        "bind_hybrid_retriever": bind_hybrid_retriever,
        "create_hybrid_retriever": create_hybrid_retriever,
        "get_hybrid_retriever": get_hybrid_retriever,
        "reset_hybrid_retriever": reset_hybrid_retriever,
    }
    return mapping[name]


__all__ = [
    "EmbeddingClientProtocol",
    "PaperChunk",
    "PaperEntity",
    "PaperRelation",
    "JudgeMicroOutput",
    "JudgeSchema",
    "QAJudgeResult",
    "SentenceJudgment",
    "SentenceLabel",
    "TrackBJudgeSchema",
    "QuestionScale",
    "RetrievalContext",
    "RetrievedChunk",
    "RetrievedEntity",
    "RetrievedRelation",
    "VectorEvidenceType",
    "VectorStore",
    "HybridRetriever",
    "bind_hybrid_retriever",
    "create_hybrid_retriever",
    "get_hybrid_retriever",
    "reset_hybrid_retriever",
    "chunk_text",
    "graph_to_entities",
    "graph_to_relations",
    "index_paper_for_rag",
]
