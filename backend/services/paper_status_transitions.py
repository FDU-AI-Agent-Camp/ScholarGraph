# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Paper lifecycle status transition ADT for PipelineStatusService writes.

Reextract resets go through ``pipeline_repo.reset_for_reextract`` (not ``_apply``).
Cold-boot / watchdog tombstones go through sync SQL helpers. Terminal RAG promote
uses ``promote_paper_to_terminal_status`` with its own INDEXING gate.

This module constrains progressive writes via ``PipelineStatusService._apply``.

Allowed surface mirrors production callers:

- ``run_paper_pipeline`` always ``start_processing`` (READY/FAILED retry → PROCESSING)
- idempotent terminal writes (READY→READY, FAILED→FAILED) for warning / error backfill
- forbid dirty jumps such as READY→INDEXING or INDEXING→PROCESSING stage rewind
"""

from __future__ import annotations

from backend.schemas.paper import PaperStatus
from backend.services.errors import InvalidStateTransitionError

# Explicit legal edges — anything else is a domain fault (no dirty reverse jump).
ALLOWED_STATUS_TRANSITIONS: frozenset[tuple[PaperStatus, PaperStatus]] = frozenset(
    {
        # Boot / queue
        (PaperStatus.PENDING, PaperStatus.PROCESSING),
        (PaperStatus.PENDING, PaperStatus.INDEXING),
        (PaperStatus.PENDING, PaperStatus.READY),
        (PaperStatus.PENDING, PaperStatus.READY_WITH_WARNINGS),
        (PaperStatus.PENDING, PaperStatus.FAILED),
        # Active extract (incl. stage advance self-loop)
        (PaperStatus.PROCESSING, PaperStatus.PROCESSING),
        (PaperStatus.PROCESSING, PaperStatus.INDEXING),
        (PaperStatus.PROCESSING, PaperStatus.READY),
        (PaperStatus.PROCESSING, PaperStatus.READY_WITH_WARNINGS),
        (PaperStatus.PROCESSING, PaperStatus.FAILED),
        # RAG index
        (PaperStatus.INDEXING, PaperStatus.INDEXING),
        (PaperStatus.INDEXING, PaperStatus.READY),
        (PaperStatus.INDEXING, PaperStatus.READY_WITH_WARNINGS),
        (PaperStatus.INDEXING, PaperStatus.FAILED),
        # Terminal idempotent + force-fail + pipeline re-entry
        (PaperStatus.READY, PaperStatus.READY),
        (PaperStatus.READY, PaperStatus.READY_WITH_WARNINGS),
        (PaperStatus.READY, PaperStatus.FAILED),
        (PaperStatus.READY, PaperStatus.PROCESSING),
        (PaperStatus.READY_WITH_WARNINGS, PaperStatus.READY_WITH_WARNINGS),
        (PaperStatus.READY_WITH_WARNINGS, PaperStatus.READY),
        (PaperStatus.READY_WITH_WARNINGS, PaperStatus.FAILED),
        (PaperStatus.READY_WITH_WARNINGS, PaperStatus.PROCESSING),
        # Fail recover: requeue OR direct pipeline retry
        (PaperStatus.FAILED, PaperStatus.FAILED),
        (PaperStatus.FAILED, PaperStatus.PENDING),
        (PaperStatus.FAILED, PaperStatus.PROCESSING),
    }
)


def assert_status_transition_allowed(
    from_status: PaperStatus,
    to_status: PaperStatus,
    *,
    paper_id: str | None = None,
) -> None:
    """Raise ``InvalidStateTransitionError`` when ``(from, to)`` is not in the ADT."""
    if (from_status, to_status) in ALLOWED_STATUS_TRANSITIONS:
        return
    raise InvalidStateTransitionError(
        f"非法状态转移: {from_status.value} → {to_status.value}",
        from_status=from_status.value,
        to_status=to_status.value,
        paper_id=paper_id,
    )
