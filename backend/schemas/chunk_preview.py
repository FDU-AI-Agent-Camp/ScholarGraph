"""Chunk citation preview state — shared BE/FE contract (B10)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ChunkPreviewState(StrEnum):
    """Machine-readable chunk ``text_preview`` resolution state."""

    READY = "ready"
    INDEXING = "indexing"
    RETRIEVAL_TIMEOUT = "retrieval_timeout"
    L2_TIMEOUT = "l2_timeout"
    HALLUCINATED_ID = "hallucinated_id"


CHUNK_PREVIEW_STATE_MESSAGES: dict[ChunkPreviewState, str] = {
    ChunkPreviewState.INDEXING: "[Context indexing in progress, please refresh later]",
    ChunkPreviewState.RETRIEVAL_TIMEOUT: "[Vector retrieval timeout, preview unavailable]",
    ChunkPreviewState.L2_TIMEOUT: "[Vector retrieval timeout, preview unavailable]",
    ChunkPreviewState.HALLUCINATED_ID: "[Reference verification failed: Hallucinated ID]",
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
