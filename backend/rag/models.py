"""Pydantic models and protocols for V2 RAG vector indexing."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field


class VectorEvidenceType(StrEnum):
    """Evidence classes stored in separate ChromaDB collections."""

    CHUNK = "chunk"
    ENTITY = "entity"
    RELATION = "relation"


class QuestionScale(StrEnum):
    """V2 retrieval scale used by the hard-rule QA router."""

    SKELETON = "skeleton"
    DETAIL = "detail"
    CROSS_PAPER = "cross"


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


class RetrievalContext(BaseModel):
    """Unified context returned by the V2 hybrid retriever."""

    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    entities: list[RetrievedEntity] = Field(default_factory=list)
    relations: list[RetrievedRelation] = Field(default_factory=list)
    chunks: list[RetrievedChunk] = Field(default_factory=list)
    scale: QuestionScale


class EmbeddingClientProtocol(Protocol):
    """Minimal embedding client contract used by VectorStore and tests."""

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""
        ...
