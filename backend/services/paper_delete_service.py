"""Cascading physical delete for papers (SQL + graph JSON + Chroma + PDF)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

from backend.api.exceptions import ApiError
from backend.config import get_settings
from backend.graph.head_store import HeadStore
from backend.graph.store import GraphStore
from backend.repositories import run_async
from backend.schemas.paper import PaperStatus
from backend.services.pipeline_task_registry import abort_in_flight_pipeline

if TYPE_CHECKING:
    from backend.services.paper_service import PaperService

logger = logging.getLogger(__name__)

VECTOR_DELETE_UNAVAILABLE_CODE = "VECTOR_STORE_UNAVAILABLE"
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
    if not pdf_path_str:
        return False
    path = Path(pdf_path_str)
    try:
        existed = path.is_file()
        path.unlink(missing_ok=True)
        return existed
    except OSError:
        logger.warning("paper_delete_pdf_unlink_failed", extra={"path": str(path)}, exc_info=True)
        return False


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
        token in message
        for token in ("timeout", "timed out", "unavailable", "connection refused", "503", "502")
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


def _purge_graph_dir_artefacts(paper_id: str) -> int:
    """Zero-footprint: unlink all GRAPH_DATA_DIR files owned by *paper_id*.

    Covers ``{id}.json``, ``{id}.head.json``, and any ``{id}.*`` / ``{id}_*`` sidecars
    (skeleton/cache naming if introduced later).
    """
    base = Path(get_settings().graph_data_dir)
    if not base.is_dir():
        return 0
    removed = 0
    for path in base.iterdir():
        if not path.is_file():
            continue
        name = path.name
        if name == f"{paper_id}.json" or name.startswith(f"{paper_id}.") or name.startswith(f"{paper_id}_"):
            try:
                path.unlink(missing_ok=True)
                removed += 1
            except OSError:
                logger.warning(
                    "paper_delete_graph_artefact_unlink_failed",
                    extra={"paper_id": paper_id, "path": str(path)},
                    exc_info=True,
                )
    return removed


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
      3) GRAPH_DATA_DIR Zero-Footprint unlink (graph / head / sidecars)
      4) uploaded PDF
      5) SQL paper row (``pipeline_runs`` CASCADE)

    Default blocks ``PROCESSING`` / ``INDEXING`` with 409; ``force=true`` aborts then cascades.
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

    # Always best-effort abort so late runners cannot ghost-write after wipe.
    await abort_in_flight_pipeline(paper_id)

    pdf_path_str = run_async(paper_service._paper_repo.get_pdf_path(paper_id))
    chroma_purged = await _purge_vector_index_hard(paper_id, vector_store=vector_store)

    # Prefer glob wipe (covers HeadStore + future sidecars); keep explicit deletes for clarity.
    graph_files_removed = _purge_graph_dir_artefacts(paper_id)
    GraphStore().delete(paper_id)
    HeadStore().delete(paper_id)
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
            },
        },
    )
