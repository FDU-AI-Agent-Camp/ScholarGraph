"""Pipeline generation (run_id) write gate for cross-worker orphan defense.

Each extract / re-extract mints a ``pipeline_generation_id`` on ``pipeline_runs``.
Task context carries that token; before GraphStore / terminal SQL writes we assert:

    current_db_generation_id == task_context.pipeline_generation_id

Watchdog / re-extract invalidate or bump the DB token so a late orphan cannot
commit ready / indexing after the row was already failed.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from backend.services.errors import ObsoletePipelineGenerationError

logger = logging.getLogger(__name__)

PIPELINE_GENERATION_GUARD_LOG = "pipeline_generation_guard_abort"


def generate_pipeline_generation_id() -> str:
    """Mint a unique, time-ordered pipeline generation token."""
    return f"plog_{datetime.now(UTC).timestamp():.6f}_{uuid.uuid4().hex[:8]}"


def assert_pipeline_generation_writable(
    paper_id: str,
    expected_generation_id: str | None,
) -> None:
    """Refuse terminal writes when the task token is obsolete or missing under a live gen.

    Legacy / test paths where neither side has a token (both ``None``) are allowed.
    Once a generation exists in DB, the caller must present the matching token.
    """
    from backend.services.paper_service import get_paper_service

    current = get_paper_service().get_pipeline_generation_id(paper_id)
    if current is None and expected_generation_id is None:
        return
    if expected_generation_id is not None and current == expected_generation_id:
        return

    message = (
        f"[Pipeline Generation Guard] Aborting database update for {paper_id}: "
        f"expected={expected_generation_id!r} current={current!r}"
    )
    logger.warning(
        PIPELINE_GENERATION_GUARD_LOG,
        extra={
            "paper_id": paper_id,
            "expected_generation_id": expected_generation_id,
            "current_generation_id": current,
            "pipeline_generation_guard": True,
        },
    )
    raise ObsoletePipelineGenerationError(
        message,
        paper_id=paper_id,
        expected_generation_id=expected_generation_id,
        current_generation_id=current,
    )
