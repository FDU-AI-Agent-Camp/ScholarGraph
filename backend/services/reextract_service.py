# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Force re-extract escape hatch for papers that fell back to heuristic graphs."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from backend.api.exceptions import ApiError
from backend.db.models import PAPER_OPS_OPERATION_REEXTRACT
from backend.graph.head_store import HeadStore
from backend.graph.store import GraphStore
from backend.schemas.paper import PaperStatus, PaperStatusData
from backend.services.paper_delete_service import (
    _VectorStoreDelete,
    resolve_vector_store_for_delete,
)
from backend.services.paper_ops_claim import (
    acquire_paper_ops_claim,
    force_release_paper_ops_claim_sync,
    is_paper_ops_claim_held,
    release_paper_ops_claim,
    reset_paper_ops_claims,
)
from backend.services.paper_pipeline_ops import get_paper_pipeline_ops_service
from backend.services.paper_pipeline_scheduler import schedule_paper_pipeline
from backend.services.pipeline_task_registry import abort_in_flight_pipeline

if TYPE_CHECKING:
    from backend.services.paper_service import PaperService

logger = logging.getLogger(__name__)

_REEXTRACT_QUEUED_MESSAGE = "已强制重新抽取，等待流水线启动…"
_ACTIVE_PIPELINE_STATUSES = frozenset({PaperStatus.PROCESSING, PaperStatus.INDEXING})


def reset_reextract_inflight_gate() -> None:
    """Drop durable wipe claims (tests / process recycle)."""
    reset_paper_ops_claims()


def is_reextract_inflight(paper_id: str) -> bool:
    """Return whether *paper_id* currently holds a wipe claim (tests / diagnostics)."""
    return is_paper_ops_claim_held(paper_id)


def release_reextract_claim_for_abort(paper_id: str) -> None:
    """Evict the wipe claim so a later reextract/delete is not stuck on 409.

    Sync-safe for the processing watchdog Cascading Kill Channel (lock eviction).
    Must **not** be invoked from ``abort_in_flight_pipeline`` while force_reextract /
    delete_paper still own the claim for the remainder of their wipe critical section.
    """
    force_release_paper_ops_claim_sync(paper_id)


def _resolve_pdf_path(pdf_path_str: str | None, paper_id: str) -> Path:
    """Return the stored PDF path or raise a 422 error if it is missing."""
    if pdf_path_str is None:
        raise ApiError(
            "PDF_NOT_FOUND",
            f"无法找到论文 {paper_id} 的原始 PDF，无法重新抽取",
            status_code=422,
        )
    pdf_path = Path(pdf_path_str)
    if not pdf_path.is_file():
        raise ApiError(
            "PDF_NOT_FOUND",
            f"无法找到论文 {paper_id} 的原始 PDF，无法重新抽取",
            status_code=422,
        )
    return pdf_path


async def _clear_persisted_artefacts(paper_id: str) -> None:
    """Remove final graph and refined head from disk (off the event loop)."""

    def _delete_sync() -> None:
        GraphStore().delete(paper_id)
        HeadStore().delete(paper_id)

    await asyncio.to_thread(_delete_sync)


async def _clear_in_memory_state(paper_id: str) -> None:
    """Reset preview and RAG run tracking for a paper."""
    await get_paper_pipeline_ops_service().clear_ephemeral_pipeline_state(paper_id)


async def _purge_vector_index(
    paper_id: str,
    *,
    vector_store: _VectorStoreDelete | None = None,
) -> None:
    """Drop Chroma rows for *paper_id* so the next pipeline cannot mix old embeddings.

    Best-effort: vector-store outages must not block the reextract escape hatch.
    """
    try:
        store = resolve_vector_store_for_delete(vector_store)
        await store.delete_by_paper(paper_id)
    except Exception:
        logger.warning(
            "reextract_vector_purge_failed",
            extra={"paper_id": paper_id},
            exc_info=True,
        )


async def force_reextract(
    paper_service: PaperService,
    paper_id: str,
    *,
    force: bool = False,
    vector_store: _VectorStoreDelete | None = None,
) -> PaperStatusData:
    """Forcefully re-run the extraction pipeline for an existing paper.

    Clears graph/head artefacts, purges Chroma for this paper, resets DB status
    to pending, bumps ``graph_version``, clears pipeline warnings, and
    re-schedules the pipeline from the stored PDF path.

    Default blocks ``PROCESSING`` and ``INDEXING`` with 409. With ``force=true``,
    cancels in-flight asyncio tasks (pipeline / head-refine / extract / indexing
    run) before reset. Best-effort abort also runs for terminal/pending paths so
    a late worker cannot resurrect stale artefacts after wipe.

    Concurrent wipe ops for the same ``paper_id`` (reextract ∪ delete) are rejected
    with 409 via durable ``paper_ops_claims``; the owner token is released in
    ``finally`` (Cascading Kill may force-evict abandoned claims).
    """
    paper = await paper_service._paper_repo.get(paper_id)
    if paper is None:
        raise ApiError("PAPER_NOT_FOUND", f"论文不存在: {paper_id}", status_code=404)

    if paper.status in _ACTIVE_PIPELINE_STATUSES and not force:
        raise ApiError(
            "PAPER_ALREADY_PROCESSING",
            f"论文 {paper_id} 正在处理或构建索引中，请等待当前任务完成；卡死时可传 force=true 强行中止并重抽",
            status_code=409,
        )

    owner_token = await acquire_paper_ops_claim(paper_id, operation=PAPER_OPS_OPERATION_REEXTRACT)
    try:
        from backend.rag.wipe_vector_sweep import (
            extend_wipe_targets_after_abort,
            schedule_wipe_wave2_sweep,
            snapshot_wipe_target_run_ids,
        )

        wipe_targets = snapshot_wipe_target_run_ids(paper_id)
        # Abort cancels Tasks / indexing revoke only — does not drop this claim.
        await abort_in_flight_pipeline(paper_id)
        wipe_targets = extend_wipe_targets_after_abort(paper_id, wipe_targets)

        pdf_path_str = await paper_service._paper_repo.get_pdf_path(paper_id)
        pdf_path = _resolve_pdf_path(pdf_path_str, paper_id)
        # Wave 1: best-effort paper-wide purge; Wave 2 hunts late run_id ghosts.
        await _purge_vector_index(paper_id, vector_store=vector_store)
        schedule_wipe_wave2_sweep(paper_id, wipe_targets)
        await _clear_persisted_artefacts(paper_id)
        await _clear_in_memory_state(paper_id)

        await paper_service._paper_repo.reset_for_reextract(paper_id)
        snapshot = await get_paper_pipeline_ops_service().reset_pipeline_for_reextract(
            paper_id,
            message=_REEXTRACT_QUEUED_MESSAGE,
        )

        schedule_paper_pipeline(paper_id, pdf_path)
        return snapshot
    finally:
        await release_paper_ops_claim(paper_id, owner_token)
