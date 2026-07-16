"""Cascading physical delete for papers (SQL + graph JSON + Chroma + PDF)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

from backend.api.exceptions import ApiError
from backend.config import get_settings
from backend.db.models import PAPER_OPS_OPERATION_DELETE
from backend.graph.head_store import HeadStore
from backend.graph.store import GraphStore
from backend.repositories import run_async
from backend.schemas.paper import PaperStatus
from backend.services.paper_ops_claim import (
    acquire_paper_ops_claim,
    release_paper_ops_claim,
)
from backend.services.pipeline_task_registry import abort_in_flight_pipeline

if TYPE_CHECKING:
    from backend.services.paper_service import PaperService

logger = logging.getLogger(__name__)

VECTOR_DELETE_UNAVAILABLE_CODE = "VECTOR_STORE_UNAVAILABLE"
DISK_ARTEFACT_DELETE_FAILED_CODE = "DISK_ARTEFACT_DELETE_FAILED"
_ACTIVE_PIPELINE_STATUSES = frozenset({PaperStatus.PROCESSING, PaperStatus.INDEXING})


class _VectorStoreDelete(Protocol):
    async def delete_by_paper(self, paper_id: str) -> None: ...


def resolve_vector_store_for_delete(
    vector_store: _VectorStoreDelete | None = None,
) -> _VectorStoreDelete:
    """Resolve a vector store that can ``delete_by_paper`` (tests may inject)."""
    if vector_store is not None:
        return vector_store
    from backend.rag.hybrid_retriever import get_hybrid_retriever

    try:
        retriever = get_hybrid_retriever()
        store = retriever.vector_store
        if store is not None and hasattr(store, "delete_by_paper"):
            # HybridRetriever types vector_store as VectorStoreProtocol (no delete);
            # runtime VectorStore / replacements implement delete_by_paper.
            return cast(_VectorStoreDelete, store)
    except Exception:
        logger.debug("hybrid_retriever_unavailable_for_delete", exc_info=True)
    from backend.rag.vector_store import VectorStore
    from backend.services.paper_service import get_paper_service

    return VectorStore(paper_service=get_paper_service())


def _resolve_vector_store(vector_store: _VectorStoreDelete | None) -> _VectorStoreDelete:
    return resolve_vector_store_for_delete(vector_store)


def _unlink_pdf(pdf_path_str: str | None) -> bool:
    """Unlink the uploaded PDF. Raise when the file still exists after the attempt."""
    if not pdf_path_str:
        return False
    path = Path(pdf_path_str)
    existed = path.is_file()
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        if path.is_file():
            raise ApiError(
                DISK_ARTEFACT_DELETE_FAILED_CODE,
                f"无法删除 PDF 残留文件，已中止级联以免留下半删除状态: {path}",
                status_code=500,
            ) from exc
        logger.warning("paper_delete_pdf_unlink_failed", extra={"path": str(path)}, exc_info=True)
        return False
    if path.is_file():
        raise ApiError(
            DISK_ARTEFACT_DELETE_FAILED_CODE,
            f"PDF 在 unlink 后仍存在，已中止级联以免留下半删除状态: {path}",
            status_code=500,
        )
    return existed


def _list_graph_dir_artefacts(paper_id: str) -> list[Path]:
    base = Path(get_settings().graph_data_dir)
    if not base.is_dir():
        return []
    owned: list[Path] = []
    for path in base.iterdir():
        if not path.is_file():
            continue
        name = path.name
        if name == f"{paper_id}.json" or name.startswith(f"{paper_id}.") or name.startswith(f"{paper_id}_"):
            owned.append(path)
    return owned


def _purge_graph_dir_artefacts(paper_id: str) -> int:
    """Zero-footprint: unlink all GRAPH_DATA_DIR files owned by *paper_id*.

    Covers ``{id}.json``, ``{id}.head.json``, and any ``{id}.*`` / ``{id}_*`` sidecars.
    Hard-fails if any owned file remains so DELETE cannot report success with residue.
    """
    owned = _list_graph_dir_artefacts(paper_id)
    removed = 0
    leftovers: list[str] = []
    for path in owned:
        try:
            path.unlink(missing_ok=True)
            removed += 1
        except OSError:
            logger.warning(
                "paper_delete_graph_artefact_unlink_failed",
                extra={"paper_id": paper_id, "path": str(path)},
                exc_info=True,
            )
        if path.is_file():
            leftovers.append(str(path))
    if leftovers:
        raise ApiError(
            DISK_ARTEFACT_DELETE_FAILED_CODE,
            f"无法清理图谱/sidecar 残留，已中止 SQL 删除以免留下半删除状态: {', '.join(leftovers)}",
            status_code=500,
        )
    return removed


def _delete_graph_stores(paper_id: str) -> None:
    """Explicit GraphStore / HeadStore deletes; soft-missing is ok, leftover file is not."""
    try:
        GraphStore().delete(paper_id)
    except OSError as exc:
        path = Path(get_settings().graph_data_dir) / f"{paper_id}.json"
        if path.is_file():
            raise ApiError(
                DISK_ARTEFACT_DELETE_FAILED_CODE,
                f"无法删除图谱 JSON 残留，已中止级联: {path}",
                status_code=500,
            ) from exc
        logger.warning("paper_delete_graph_store_failed", extra={"paper_id": paper_id}, exc_info=True)
    try:
        HeadStore().delete(paper_id)
    except OSError as exc:
        path = Path(get_settings().graph_data_dir) / f"{paper_id}.head.json"
        if path.is_file():
            raise ApiError(
                DISK_ARTEFACT_DELETE_FAILED_CODE,
                f"无法删除 head JSON 残留，已中止级联: {path}",
                status_code=500,
            ) from exc
        logger.warning("paper_delete_head_store_failed", extra={"paper_id": paper_id}, exc_info=True)


def _is_vector_not_found_error(exc: BaseException) -> bool:
    """Chroma / FS 'missing' outcomes are success for DELETE (nothing to erase)."""
    name = type(exc).__name__.lower()
    if "notfound" in name or name in {"filenotfounderror", "keyerror"}:
        return True
    message = str(exc).lower()
    return "not found" in message or "404" in message or "does not exist" in message


def _is_vector_unavailable_error(exc: BaseException) -> bool:
    """Timeouts / connectivity failures must hard-fail DELETE (no SQL wipe)."""
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return True
    name = type(exc).__name__.lower()
    if any(token in name for token in ("timeout", "unavailable", "connection", "connect")):
        return True
    message = str(exc).lower()
    return any(
        token in message for token in ("timeout", "timed out", "unavailable", "connection refused", "503", "502")
    )


async def _purge_vector_index_hard(
    paper_id: str,
    *,
    vector_store: _VectorStoreDelete | None = None,
) -> bool:
    """Delete Chroma rows for *paper_id*.

    - Missing / empty (404-class) → treat as success, return False (nothing deleted).
    - Timeout / cluster down → raise ApiError 503 (do not continue to SQL).
    """
    store = _resolve_vector_store(vector_store)
    try:
        await store.delete_by_paper(paper_id)
        return True
    except Exception as exc:
        if _is_vector_not_found_error(exc):
            logger.info(
                "paper_delete_vector_already_absent",
                extra={"paper_id": paper_id, "exc_type": type(exc).__name__},
            )
            return False
        if _is_vector_unavailable_error(exc):
            raise ApiError(
                VECTOR_DELETE_UNAVAILABLE_CODE,
                f"向量库暂不可用，无法安全删除论文 {paper_id}；请稍后重试以免留下幽灵向量",
                status_code=503,
            ) from exc
        raise ApiError(
            VECTOR_DELETE_UNAVAILABLE_CODE,
            f"向量索引清理失败，已中止删除以免留下幽灵向量: {type(exc).__name__}",
            status_code=503,
        ) from exc


async def delete_paper(
    paper_service: PaperService,
    paper_id: str,
    *,
    force: bool = False,
    vector_store: _VectorStoreDelete | None = None,
) -> None:
    """Physically remove a paper and all RAG artefacts.

    Order (must not reverse):
      1) abort in-flight tasks (after 409 gate)
      2) Chroma ``delete_by_paper`` (hard-fail on unavailable; 404-class = ok)
      3) GRAPH_DATA_DIR Zero-Footprint unlink (graph / head / sidecars) — hard-fail on residue
      4) uploaded PDF — hard-fail on residue
      5) SQL paper row (``pipeline_runs`` CASCADE)

    Default blocks ``PROCESSING`` / ``INDEXING`` with 409; ``force=true`` aborts then cascades.

    Concurrent wipe ops for the same ``paper_id`` (delete ∪ reextract) are rejected
    with 409 via durable ``paper_ops_claims`` for the critical section duration.
    """
    paper = run_async(paper_service._paper_repo.get(paper_id))
    if paper is None:
        raise ApiError("PAPER_NOT_FOUND", f"论文不存在: {paper_id}", status_code=404)

    if paper.status in _ACTIVE_PIPELINE_STATUSES and not force:
        raise ApiError(
            "PAPER_ALREADY_PROCESSING",
            f"论文 {paper_id} 正在处理或构建索引中，请先取消或传 force=true 强行中止并删除",
            status_code=409,
        )

    owner_token = await acquire_paper_ops_claim(paper_id, operation=PAPER_OPS_OPERATION_DELETE)
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

        pdf_path_str = run_async(paper_service._paper_repo.get_pdf_path(paper_id))
        # Wave 1: immediate paper-wide Chroma purge (hard-fail if Chroma is down).
        chroma_purged = await _purge_vector_index_hard(paper_id, vector_store=vector_store)
        # Wave 2: delayed delete_run for revoked / prior active ids (late to_thread upserts).
        schedule_wipe_wave2_sweep(paper_id, wipe_targets)

        # Prefer glob wipe (covers HeadStore + future sidecars); keep explicit deletes for clarity.
        graph_files_removed = _purge_graph_dir_artefacts(paper_id)
        _delete_graph_stores(paper_id)
        paper_service.clear_ephemeral_pipeline_state(paper_id)
        pdf_removed = _unlink_pdf(pdf_path_str)

        deleted = run_async(paper_service._paper_repo.delete(paper_id))
        if not deleted:
            raise ApiError("PAPER_NOT_FOUND", f"论文不存在: {paper_id}", status_code=404)

        logger.info(
            "Cascade delete completed for paper_id=%s",
            paper_id,
            extra={
                "paper_id": paper_id,
                "force": force,
                "details": {
                    "chroma": chroma_purged,
                    "graph_files": graph_files_removed,
                    "pdf": pdf_removed,
                    "sql": True,
                    "wipe_wave2_runs": sorted(wipe_targets),
                },
            },
        )
    finally:
        await release_paper_ops_claim(paper_id, owner_token)
