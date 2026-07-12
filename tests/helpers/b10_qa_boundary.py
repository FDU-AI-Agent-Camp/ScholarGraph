"""Shared helpers for B10 chunk-preview boundary / E2E tests."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from backend.graph.qa import QaEvent
from backend.schemas.paper import PaperDetail, PaperStatus
from backend.schemas.paradigm import Paradigm
from backend.services.paper_service import PaperService


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


def register_processing_paper(
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
        service.mark_preview_available(paper_id)
    return paper
