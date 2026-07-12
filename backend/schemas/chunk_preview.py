"""Chunk citation preview state — shared BE/FE contract (B10)."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from backend.rag.models import (
    CHUNK_PREVIEW_DEGRADED_WHITELIST,
    ChunkPreviewDegradedMessage,
)


class ChunkPreviewState(StrEnum):
    """Machine-readable chunk ``text_preview`` resolution state."""

    READY = "ready"
    INDEXING = "indexing"
    RETRIEVAL_TIMEOUT = "retrieval_timeout"
    L2_TIMEOUT = "l2_timeout"
    HALLUCINATED_ID = "hallucinated_id"


CHUNK_PREVIEW_STATE_MESSAGES: dict[ChunkPreviewState, str] = {
    ChunkPreviewState.INDEXING: ChunkPreviewDegradedMessage.INDEXING.value,
    ChunkPreviewState.RETRIEVAL_TIMEOUT: ChunkPreviewDegradedMessage.VECTOR_RETRIEVAL_TIMEOUT.value,
    ChunkPreviewState.L2_TIMEOUT: ChunkPreviewDegradedMessage.VECTOR_RETRIEVAL_TIMEOUT.value,
    ChunkPreviewState.HALLUCINATED_ID: ChunkPreviewDegradedMessage.HALLUCINATED_ID.value,
}

CHUNK_TEXT_PREVIEW_MAX_CHARS = 120


def chunk_preview_message(state: ChunkPreviewState) -> str:
    """Return the canonical degraded ``text_preview`` copy for *state*."""
    message = CHUNK_PREVIEW_STATE_MESSAGES.get(state)
    if message is None:
        msg = f"no preview message for state: {state}"
        raise ValueError(msg)
    return message


def truncate_chunk_preview(text: str) -> str:
    """Trim preview to the SSE contract limit (≤120 chars)."""
    return text[:CHUNK_TEXT_PREVIEW_MAX_CHARS]


class ResolvedChunkPreview(BaseModel):
    """Validated chunk citation preview payload fragment."""

    text_preview: str = Field(max_length=CHUNK_TEXT_PREVIEW_MAX_CHARS)
    preview_state: ChunkPreviewState

    @classmethod
    def ready(cls, text: str) -> ResolvedChunkPreview:
        return cls(text_preview=truncate_chunk_preview(text), preview_state=ChunkPreviewState.READY)

    @classmethod
    def degraded(cls, state: ChunkPreviewState) -> ResolvedChunkPreview:
        if state == ChunkPreviewState.READY:
            msg = "degraded() requires a non-ready state"
            raise ValueError(msg)
        return cls(text_preview=chunk_preview_message(state), preview_state=state)


class QaStreamCitationChunkContract(BaseModel):
    """Strict SSE chunk citation contract — enforces ``preview_state`` ↔ ``text_preview`` lockstep."""

    type: Literal["chunk"]
    paper_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    text_preview: str = Field(min_length=1, max_length=CHUNK_TEXT_PREVIEW_MAX_CHARS)
    preview_state: ChunkPreviewState

    @model_validator(mode="after")
    def verify_text_preview_whitelist(self) -> Self:
        """Reject ad-hoc degraded copy; ready previews must not reuse placeholder strings."""
        is_whitelisted = self.text_preview in CHUNK_PREVIEW_DEGRADED_WHITELIST

        if self.preview_state == ChunkPreviewState.READY:
            if is_whitelisted:
                msg = "ready preview_state must not emit degraded placeholder text_preview"
                raise ValueError(msg)
            return self

        expected = CHUNK_PREVIEW_STATE_MESSAGES.get(self.preview_state)
        if expected is None:
            msg = f"no canonical text_preview for preview_state={self.preview_state!r}"
            raise ValueError(msg)
        if self.text_preview != expected:
            msg = (
                f"degraded text_preview must match ChunkPreviewDegradedMessage whitelist: "
                f"expected {expected!r}, got {self.text_preview!r}"
            )
            raise ValueError(msg)
        return self
