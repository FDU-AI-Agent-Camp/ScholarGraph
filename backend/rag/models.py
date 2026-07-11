"""Pydantic models and protocols for V2 RAG vector indexing (Phase 1+2+4)."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Question-scale routing (Phase 2 — rag-qa-evaluation / rag-hybrid-retriever)
# ---------------------------------------------------------------------------


class QuestionScale(StrEnum):
    """Three-scale routing for hybrid RAG."""

    SKELETON = "skeleton"  # 摘要 / 整体结构 — A 尺度
    DETAIL = "detail"  # 方法 / 数据 / 实验数值 — B 尺度
    CROSS_PAPER = "cross"  # 多篇对比（未来）


class VectorEvidenceType(StrEnum):
    """Evidence classes stored in separate ChromaDB collections."""

    CHUNK = "chunk"
    ENTITY = "entity"
    RELATION = "relation"


class PaperChunk(BaseModel):
    """A searchable slice of original paper text."""

    chunk_id: str = Field(min_length=1)
    paper_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    page_start: int | None = None
    page_end: int | None = None
    section: str | None = None
    chunk_index: int = Field(ge=0)
    source: str = Field(default="pymupdf", min_length=1)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)


class PaperEntity(BaseModel):
    """A graph node converted into searchable vector evidence."""

    entity_id: str = Field(min_length=1)
    paper_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    node_type: str = Field(min_length=1)
    description: str = Field(min_length=1)
    source_span: str | None = None


class PaperRelation(BaseModel):
    """A graph edge converted into searchable vector evidence."""

    relation_id: str = Field(min_length=1)
    paper_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    relation_type: str = Field(min_length=1)
    description: str = Field(min_length=1)
    rationale: str | None = None
    source_span: str | None = None


class RetrievedEvidence(BaseModel):
    """Common fields shared by all retrieved RAG evidence types."""

    id: str = Field(min_length=1, description="Namespaced ChromaDB id.")
    paper_id: str = Field(min_length=1)
    text: str
    distance: float | None = None


class RetrievedChunk(RetrievedEvidence):
    """A retrieved original-text chunk, ready for downstream generation."""

    evidence_type: VectorEvidenceType = VectorEvidenceType.CHUNK
    chunk_id: str = Field(min_length=1)
    section: str | None = None
    chunk_index: int = Field(ge=0)
    source: str = Field(default="pymupdf", min_length=1)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    page_start: int | None = None
    page_end: int | None = None


class RetrievedEntity(RetrievedEvidence):
    """A retrieved graph entity, ready for downstream generation."""

    evidence_type: VectorEvidenceType = VectorEvidenceType.ENTITY
    entity_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    node_type: str = Field(min_length=1)
    source_span: str | None = None


class RetrievedRelation(RetrievedEvidence):
    """A retrieved graph relation, ready for downstream generation."""

    evidence_type: VectorEvidenceType = VectorEvidenceType.RELATION
    relation_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    relation_type: str = Field(min_length=1)
    rationale: str | None = None
    source_span: str | None = None


class EmbeddingClientProtocol(Protocol):
    """Minimal embedding client contract used by VectorStore and tests."""

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""
        ...


# ---------------------------------------------------------------------------
# Retrieval context (Phase 2 — consumed by QA + Patrol)
# ---------------------------------------------------------------------------


class QAJudgeResult(BaseModel):
    """Structured output from the LLM-as-a-Judge QA evaluation pass (Track B)."""

    factual_consistency: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Score from 0.0 to 1.0 indicating semantic alignment of facts with the golden context.",
    )
    hallucination_detected: bool = Field(
        ...,
        description="True if the model answer contains facts or logical claims contradictory to or unsupported by context.",
    )
    reasoning: str = Field(
        ...,
        min_length=1,
        description="Detailed justification for the above metrics.",
    )


class RetrievalContext(BaseModel):
    """Complete retrieval result passed to QA / Patrol prompt builders.

    Members:
        nodes / edges: graph topology subgraph (A 尺度).
        entities / relations / chunks: vector recall results (B 尺度).
        scale: the resolved question scale.
    """

    nodes: list[dict] = Field(default_factory=list)
    edges: list[dict] = Field(default_factory=list)
    entities: list[RetrievedEntity] = Field(default_factory=list)
    relations: list[RetrievedRelation] = Field(default_factory=list)
    chunks: list[RetrievedChunk] = Field(default_factory=list)
    scale: QuestionScale
