# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Service facade for cluster-wide paper wipe claims (delete ∪ reextract).

Part of the force-wipe lifecycle (see ``backend.rag.wipe_vector_sweep``)::

    claim (this module) → abort → Wave1 delete_by_paper → Wave2 delayed delete_run
    + read-time ``index_run_id`` filter so late upserts stay logically dead.

Durable ``paper_ops_claims`` rows replace the process-local ``_reextract_inflight``
set so multi-worker force wipe cannot interleave.
"""

from __future__ import annotations

from backend.api.exceptions import ApiError
from backend.db.models import PAPER_OPS_OPERATION_DELETE, PAPER_OPS_OPERATION_REEXTRACT
from backend.repositories.paper_ops_claim_repository import (
    PaperOpsClaimConflictError,
    get_paper_ops_claim_repository,
    reset_paper_ops_claim_repository,
)

__all__ = [
    "PAPER_OPS_OPERATION_DELETE",
    "PAPER_OPS_OPERATION_REEXTRACT",
    "acquire_paper_ops_claim",
    "force_release_paper_ops_claim",
    "force_release_paper_ops_claim_sync",
    "is_paper_ops_claim_held",
    "release_paper_ops_claim",
    "reset_paper_ops_claims",
]


def _conflict_api_error(paper_id: str, *, operation: str) -> ApiError:
    if operation == PAPER_OPS_OPERATION_DELETE:
        detail = f"论文 {paper_id} 正在删除或强制清理中，请勿重复提交"
    else:
        detail = f"论文 {paper_id} 正在强制重新抽取或清理中，请勿重复提交"
    return ApiError(
        "PAPER_ALREADY_PROCESSING",
        detail,
        status_code=409,
    )


async def acquire_paper_ops_claim(paper_id: str, *, operation: str) -> str:
    """Acquire the durable wipe mutex or raise ApiError 409."""
    repo = get_paper_ops_claim_repository()
    try:
        return await repo.try_acquire(paper_id, operation=operation)
    except PaperOpsClaimConflictError as exc:
        raise _conflict_api_error(paper_id, operation=operation) from exc


async def release_paper_ops_claim(paper_id: str, owner_token: str) -> None:
    await get_paper_ops_claim_repository().release(paper_id, owner_token)


async def force_release_paper_ops_claim(paper_id: str) -> None:
    """Evict any claim (async). Prefer sync helper from the watchdog thread."""
    await get_paper_ops_claim_repository().force_release(paper_id)


def force_release_paper_ops_claim_sync(paper_id: str) -> None:
    """Evict any claim — Cascading Kill / abort lock reflux (sync-safe)."""
    get_paper_ops_claim_repository().force_release_sync(paper_id)


def is_paper_ops_claim_held(paper_id: str) -> bool:
    """Diagnostics / tests: whether a non-expired claim exists."""
    return get_paper_ops_claim_repository().is_held_sync(paper_id)


def reset_paper_ops_claims() -> None:
    """Test helper: clear all claim rows and drop repository singleton."""
    get_paper_ops_claim_repository().clear_all_sync()
    reset_paper_ops_claim_repository()
