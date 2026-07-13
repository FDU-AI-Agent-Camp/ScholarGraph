"""Persist event-bus handler failures into pipeline extract_warnings."""

from __future__ import annotations

from typing import Any

from backend.events.types import EventType

EVENT_HANDLER_FAILED_CODE = "event_handler_failed"
MAX_HANDLER_ERROR_SUMMARY_CHARS = 200


def format_handler_failure_warning(event_type: EventType, exc: Exception) -> str:
    """Build a compact, user-visible extract_warning row for bus-level handler crashes."""
    summary = str(exc).strip() or exc.__class__.__name__
    if len(summary) > MAX_HANDLER_ERROR_SUMMARY_CHARS:
        summary = f"{summary[: MAX_HANDLER_ERROR_SUMMARY_CHARS - 3]}..."
    return f"{EVENT_HANDLER_FAILED_CODE}: Handler {event_type.value} failed: {summary}"


async def persist_event_handler_failure(
    event_type: EventType,
    exc: Exception,
    event: Any,
) -> None:
    """Record handler crash summary in ``pipeline_runs.extract_warnings`` (D12 safety net)."""
    paper_id = getattr(event, "paper_id", None)
    if not isinstance(paper_id, str) or not paper_id.strip():
        return

    from backend.services.paper_service import get_paper_service

    warning = format_handler_failure_warning(event_type, exc)
    get_paper_service().record_extract_warnings(paper_id, [warning])
