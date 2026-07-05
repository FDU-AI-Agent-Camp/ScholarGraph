"""Pydantic models and protocols for V2 RAG vector indexing."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, Field


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


class VectorSearchResult(BaseModel):
    """Unified return shape for ChromaDB search results."""

    id: str = Field(min_length=1, description="Namespaced ChromaDB id.")
    paper_id: str = Field(min_length=1)
    evidence_type: VectorEvidenceType
    text: str
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)
    distance: float | None = None


class EmbeddingClientProtocol(Protocol):
    """Minimal embedding client contract used by VectorStore and tests."""

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""
        ...
