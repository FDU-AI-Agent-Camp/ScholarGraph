"""Cascading physical delete for papers (SQL + graph JSON + Chroma + PDF)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

from backend.api.exceptions import ApiError
from backend.graph.head_store import HeadStore
from backend.graph.store import GraphStore
from backend.repositories import run_async
from backend.schemas.paper import PaperStatus
from backend.services.pipeline_task_registry import abort_in_flight_pipeline

if TYPE_CHECKING:
    from backend.services.paper_service import PaperService

logger = logging.getLogger(__name__)


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


def _unlink_pdf(pdf_path_str: str | None) -> None:
    if not pdf_path_str:
        return
    path = Path(pdf_path_str)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("paper_delete_pdf_unlink_failed", extra={"path": str(path)}, exc_info=True)


async def delete_paper(
    paper_service: PaperService,
    paper_id: str,
    *,
    force: bool = False,
    vector_store: _VectorStoreDelete | None = None,
) -> None:
    """Physically remove a paper and all RAG artefacts.

    Order (must not reverse):
      1) abort in-flight tasks when force / processing
      2) Chroma ``delete_by_paper``
      3) GraphStore / HeadStore JSON
      4) uploaded PDF
      5) SQL paper row (``pipeline_runs`` CASCADE)
    """
    paper = run_async(paper_service._paper_repo.get(paper_id))
    if paper is None:
        raise ApiError("PAPER_NOT_FOUND", f"论文不存在: {paper_id}", status_code=404)

    if paper.status == PaperStatus.PROCESSING and not force:
        raise ApiError(
            "PAPER_ALREADY_PROCESSING",
            f"论文 {paper_id} 正在解析中，请先取消或传 force=true 强行中止并删除",
            status_code=409,
        )

    # Always best-effort abort so late runners cannot ghost-write after wipe.
    await abort_in_flight_pipeline(paper_id)

    pdf_path_str = run_async(paper_service._paper_repo.get_pdf_path(paper_id))
    store = _resolve_vector_store(vector_store)
    await store.delete_by_paper(paper_id)
    GraphStore().delete(paper_id)
    HeadStore().delete(paper_id)
    paper_service.clear_ephemeral_pipeline_state(paper_id)
    _unlink_pdf(pdf_path_str)

    deleted = run_async(paper_service._paper_repo.delete(paper_id))
    if not deleted:
        raise ApiError("PAPER_NOT_FOUND", f"论文不存在: {paper_id}", status_code=404)
    logger.info("paper_cascading_delete_complete", extra={"paper_id": paper_id, "force": force})
