# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for B10 chunk-preview boundary / E2E tests."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from backend.graph.qa import QaEvent
from backend.schemas.paper import PaperDetail, PaperStatus
from backend.schemas.paradigm import Paradigm
from backend.services.paper_service import PaperService

from tests.helpers.chunk_preview_contract import enforce_chunk_citation_contract

if TYPE_CHECKING:
    from httpx import Response


class ChunkPreviewLeakError(AssertionError):
    """Raised when a mid-stream chunk citation emits an empty ``text_preview``."""


def parse_sse_frame(frame: str) -> tuple[str, dict] | None:
    """Parse one SSE frame (``event:\\n...\\ndata:\\n...``) into ``(name, payload)``."""
    event_name = "message"
    data_line: str | None = None
    for line in frame.splitlines():
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_line = line.split(":", 1)[1].strip()
    if data_line is None:
        return None
    return event_name, json.loads(data_line)


def parse_sse_body(body: str) -> list[tuple[str, dict]]:
    """Parse raw SSE text into ``(event_name, payload)`` tuples."""
    events: list[tuple[str, dict]] = []
    event_name = "message"
    for line in body.splitlines():
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            payload = json.loads(line.split(":", 1)[1].strip())
            events.append((event_name, payload))
    return events


def _audit_chunk_payload(
    data: dict,
    *,
    stream_index: int,
    transport: str,
    expected_substrings: tuple[str, ...] | None,
) -> None:
    preview = data.get("text_preview")
    if preview is None or preview == "":
        raise ChunkPreviewLeakError(
            f"Leak Detected ({transport} #{stream_index}): empty chunk text_preview mid-stream: {data!r}",
        )
    if expected_substrings and not any(sub in str(preview) for sub in expected_substrings):
        raise ChunkPreviewLeakError(
            f"Unexpected preview ({transport} #{stream_index}): {preview!r} expected one of {expected_substrings!r}",
        )
    enforce_chunk_citation_contract(data)


async def audit_qa_stream_chunk_citations(
    stream: AsyncIterator[QaEvent],
    *,
    min_chunk_citations: int = 1,
    expected_substrings: tuple[str, ...] | None = None,
    on_chunk: Callable[[dict, int], None] | None = None,
) -> list[dict]:
    """Event-level audit: inspect each ``qa_stream`` citation as it is yielded."""
    chunk_events: list[dict] = []
    stream_index = 0
    async for evt in stream:
        stream_index += 1
        if evt.event != "citation" or evt.data.get("type") != "chunk":
            continue
        _audit_chunk_payload(
            evt.data,
            stream_index=stream_index,
            transport="qa_stream",
            expected_substrings=expected_substrings,
        )
        chunk_events.append(evt.data)
        if on_chunk is not None:
            on_chunk(evt.data, stream_index)
    if len(chunk_events) < min_chunk_citations:
        msg = f"Sanity check failed: expected ≥{min_chunk_citations} chunk citations, got {len(chunk_events)}"
        raise AssertionError(msg)
    return chunk_events


async def audit_http_sse_chunk_citations(
    response: Response,
    *,
    min_chunk_citations: int = 1,
    expected_substrings: tuple[str, ...] | None = None,
) -> list[dict]:
    """Raw wire audit: parse SSE frames incrementally from ``response.aiter_text()``."""
    buffer = ""
    chunk_events: list[dict] = []
    frame_index = 0
    async for raw in response.aiter_text():
        buffer += raw
        while "\n\n" in buffer:
            frame, buffer = buffer.split("\n\n", 1)
            if not frame.strip():
                continue
            parsed = parse_sse_frame(frame)
            if parsed is None:
                continue
            event_name, payload = parsed
            frame_index += 1
            if event_name != "citation" or payload.get("type") != "chunk":
                continue
            _audit_chunk_payload(
                payload,
                stream_index=frame_index,
                transport="http_sse",
                expected_substrings=expected_substrings,
            )
            chunk_events.append(payload)
    if len(chunk_events) < min_chunk_citations:
        msg = f"Sanity check failed: expected ≥{min_chunk_citations} chunk citations, got {len(chunk_events)}"
        raise AssertionError(msg)
    return chunk_events


def chunk_citations(events: list[tuple[str, dict]]) -> list[dict]:
    """Extract chunk citation payloads from parsed SSE events."""
    return [payload for name, payload in events if name == "citation" and payload.get("type") == "chunk"]


async def collect_qa_events(
    stream: AsyncIterator[QaEvent],
) -> list[tuple[str, dict]]:
    """Drain a ``qa_stream`` async iterator into event tuples."""
    events: list[tuple[str, dict]] = []
    async for evt in stream:
        events.append((evt.event, evt.data))
    return events


async def register_processing_paper(
    service: PaperService,
    paper_id: str,
    *,
    paradigm: Paradigm = Paradigm.STEM,
    preview_available: bool = True,
) -> PaperDetail:
    """Insert a PROCESSING paper with optional MVP preview flag (cold-start QA)."""
    now = datetime.now(UTC)
    paper = PaperDetail(
        paper_id=paper_id,
        title=f"B10 boundary {paper_id}",
        paradigm=paradigm,
        status=PaperStatus.PROCESSING,
        preview_available=preview_available,
        created_at=now,
        updated_at=now,
    )
    service._papers[paper_id] = paper
    if preview_available:
        await service.mark_preview_available(paper_id)
    return paper
