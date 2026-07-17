# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""B6 gate: OpenAPI documents V2 QA SSE citation payloads."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from backend.graph.qa_v2 import dispatch_citation
from backend.schemas.chunk_preview import QaStreamCitationChunkContract
from tests.helpers.chunk_preview_contract import enforce_chunk_citation_contract

REPO_ROOT = Path(__file__).resolve().parents[2]
OPENAPI = REPO_ROOT / "docs" / "api" / "openapi.yaml"
SSE_DOC = REPO_ROOT / "docs" / "api" / "sse-qa.md"
FIXTURE = REPO_ROOT / "docs" / "api" / "fixtures" / "qa-stream-v2-frames.json"

_CITATION_REQUIRED: dict[str, set[str]] = {
    "node": {"type", "paper_id", "node_id", "label"},
    "edge": {"type", "paper_id", "edge_id", "label"},
    "chunk": {"type", "paper_id", "chunk_id", "label", "text_preview", "preview_state"},
    "page": {"type", "paper_id", "page", "label"},
}


def _assert_citation_payload(payload: dict[str, Any]) -> None:
    cite_type = payload["type"]
    assert cite_type in _CITATION_REQUIRED
    assert _CITATION_REQUIRED[cite_type] <= payload.keys()


def test_b6_openapi_qa_stream_citation_discriminator() -> None:
    spec = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    citation = spec["components"]["schemas"]["QaStreamCitation"]
    assert citation["discriminator"]["propertyName"] == "type"
    mapping = citation["discriminator"]["mapping"]
    assert set(mapping.keys()) == set(_CITATION_REQUIRED.keys())


def test_b6_openapi_qa_stream_citation_schemas_match_dispatch() -> None:
    spec = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    node = spec["components"]["schemas"]["QaStreamCitationNode"]["properties"]
    assert set(node.keys()) >= {"type", "paper_id", "node_id", "label"}

    chunk = spec["components"]["schemas"]["QaStreamCitationChunk"]["properties"]
    assert "text_preview" in chunk
    assert chunk["text_preview"].get("maxLength") == 120
    assert "preview_state" in chunk
    assert chunk["preview_state"]["$ref"] == "#/components/schemas/ChunkPreviewState"

    page = spec["components"]["schemas"]["QaStreamCitationPage"]["properties"]
    assert "page" in page


def test_b6_sse_qa_doc_and_fixture_exist() -> None:
    assert SSE_DOC.is_file()
    text = SSE_DOC.read_text(encoding="utf-8")
    assert "QaStreamCitation" in text or "type" in text
    assert FIXTURE.is_file()


def test_b6_fixture_frames_validate_against_openapi_fields() -> None:
    frames = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for frame in frames:
        if frame["event"] != "citation":
            continue
        _assert_citation_payload(frame["data"])
        if frame["data"].get("type") == "chunk":
            enforce_chunk_citation_contract(frame["data"])


def test_b6_dispatch_citation_outputs_match_openapi_fields() -> None:
    node_cache = {"n1": "核心论点"}
    edge_cache = {"e1": "分论点 → 核心论点"}
    chunk_cache = {"c1": "制度一旦形成便会产生路径依赖。"}

    events = [
        dispatch_citation("", "n1", "hss-001", node_cache, edge_cache, chunk_cache),
        dispatch_citation("edge:", "e1", "hss-001", node_cache, edge_cache, chunk_cache),
        dispatch_citation("chunk:", "c1", "hss-001", node_cache, edge_cache, chunk_cache),
        dispatch_citation("page:", "12", "hss-001", node_cache, edge_cache, chunk_cache),
    ]
    for evt in events:
        assert evt.event == "citation"
        _assert_citation_payload(evt.data)
        if evt.data.get("type") == "chunk":
            validated = QaStreamCitationChunkContract.model_validate(evt.data)
            assert validated.preview_state is not None
