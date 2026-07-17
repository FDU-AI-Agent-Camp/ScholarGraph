# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""B10 contract gate — degraded ``text_preview`` whitelist + Pydantic enforcement."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from backend.graph.qa_v2 import dispatch_citation
from backend.rag.models import CHUNK_PREVIEW_DEGRADED_WHITELIST, ChunkPreviewDegradedMessage
from backend.schemas.chunk_preview import (
    CHUNK_PREVIEW_STATE_MESSAGES,
    CHUNK_TEXT_PREVIEW_MAX_CHARS,
    ChunkPreviewState,
    QaStreamCitationChunkContract,
)
from pydantic import ValidationError
from tests.helpers.chunk_preview_contract import (
    ChunkPreviewContractError,
    enforce_chunk_citation_contract,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "docs" / "api" / "fixtures" / "qa-stream-v2-frames.json"


def _chunk_payload(**overrides: object) -> dict:
    base = {
        "type": "chunk",
        "paper_id": "hss-001",
        "chunk_id": "hss-001-00001",
        "label": "片段 hss-001-00001",
        "text_preview": "制度一旦形成便会产生路径依赖。",
        "preview_state": ChunkPreviewState.READY,
    }
    base.update(overrides)
    return base


def test_degraded_message_enum_is_whitelist_ssot() -> None:
    assert len(ChunkPreviewDegradedMessage) == 3
    assert CHUNK_PREVIEW_DEGRADED_WHITELIST == frozenset(
        {
            ChunkPreviewDegradedMessage.INDEXING.value,
            ChunkPreviewDegradedMessage.VECTOR_RETRIEVAL_TIMEOUT.value,
            ChunkPreviewDegradedMessage.HALLUCINATED_ID.value,
        },
    )


def test_state_messages_derive_from_degraded_enum() -> None:
    for state, message in CHUNK_PREVIEW_STATE_MESSAGES.items():
        assert message in CHUNK_PREVIEW_DEGRADED_WHITELIST, state
    assert (
        CHUNK_PREVIEW_STATE_MESSAGES[ChunkPreviewState.RETRIEVAL_TIMEOUT]
        == CHUNK_PREVIEW_STATE_MESSAGES[ChunkPreviewState.L2_TIMEOUT]
        == ChunkPreviewDegradedMessage.VECTOR_RETRIEVAL_TIMEOUT.value
    )


@pytest.mark.parametrize(
    ("state", "message"),
    [(state, CHUNK_PREVIEW_STATE_MESSAGES[state]) for state in CHUNK_PREVIEW_STATE_MESSAGES],
)
def test_contract_accepts_each_degraded_state(state: ChunkPreviewState, message: str) -> None:
    payload = _chunk_payload(text_preview=message, preview_state=state)
    validated = QaStreamCitationChunkContract.model_validate(payload)
    assert validated.preview_state == state
    assert validated.text_preview == message


def test_contract_accepts_ready_real_excerpt() -> None:
    payload = _chunk_payload(
        text_preview="ResNet-Light achieves 78.5% top-1 accuracy on ImageNet.",
        preview_state=ChunkPreviewState.READY,
    )
    validated = enforce_chunk_citation_contract(payload)
    assert validated.preview_state == ChunkPreviewState.READY


@pytest.mark.parametrize(
    "bad_preview",
    [
        "[Timeout]",
        "[Vector retrieval timeout]",
        "[Context indexing in progress]",
        "preview unavailable",
    ],
)
def test_contract_rejects_ad_hoc_degraded_copy(bad_preview: str) -> None:
    payload = _chunk_payload(text_preview=bad_preview, preview_state=ChunkPreviewState.RETRIEVAL_TIMEOUT)
    with pytest.raises(ValidationError):
        QaStreamCitationChunkContract.model_validate(payload)


def test_contract_rejects_ready_state_with_placeholder_text() -> None:
    payload = _chunk_payload(
        text_preview=ChunkPreviewDegradedMessage.INDEXING.value,
        preview_state=ChunkPreviewState.READY,
    )
    with pytest.raises(ValidationError, match="ready preview_state must not emit degraded"):
        QaStreamCitationChunkContract.model_validate(payload)


def test_contract_rejects_degraded_state_with_real_excerpt() -> None:
    payload = _chunk_payload(
        text_preview="制度一旦形成便会产生路径依赖。",
        preview_state=ChunkPreviewState.INDEXING,
    )
    with pytest.raises(ValidationError, match="must match ChunkPreviewDegradedMessage whitelist"):
        QaStreamCitationChunkContract.model_validate(payload)


def test_enforce_helper_wraps_validation_error() -> None:
    with pytest.raises(ChunkPreviewContractError, match="contract violation"):
        enforce_chunk_citation_contract(_chunk_payload(text_preview="[Timeout]", preview_state="retrieval_timeout"))


def test_openapi_fixture_chunk_frame_passes_contract() -> None:
    frames = json.loads(FIXTURE.read_text(encoding="utf-8"))
    chunk_frames = [
        frame for frame in frames if frame.get("event") == "citation" and frame["data"].get("type") == "chunk"
    ]
    assert chunk_frames, "fixture must include at least one chunk citation"
    for frame in chunk_frames:
        enforce_chunk_citation_contract(frame["data"])


def test_dispatch_citation_chunk_output_passes_contract() -> None:
    chunk_cache = {"c1": "制度一旦形成便会产生路径依赖。"}
    evt = dispatch_citation("chunk:", "c1", "hss-001", {}, {}, chunk_cache)
    assert evt.event == "citation"
    validated = enforce_chunk_citation_contract(evt.data)
    assert validated.preview_state == ChunkPreviewState.READY
    assert len(validated.text_preview) <= CHUNK_TEXT_PREVIEW_MAX_CHARS
