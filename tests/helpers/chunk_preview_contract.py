"""Pydantic contract enforcement for B10 chunk citation SSE payloads."""

from __future__ import annotations

from backend.schemas.chunk_preview import QaStreamCitationChunkContract
from pydantic import ValidationError


class ChunkPreviewContractError(AssertionError):
    """Raised when a chunk citation violates the ``text_preview`` whitelist contract."""


def enforce_chunk_citation_contract(data: dict) -> QaStreamCitationChunkContract:
    """Validate *data* against the strict chunk citation schema; fail tests on drift."""
    try:
        return QaStreamCitationChunkContract.model_validate(data)
    except ValidationError as exc:
        raise ChunkPreviewContractError(f"Chunk citation contract violation: {exc}") from exc
