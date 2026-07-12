"""Force re-extract escape hatch for papers that fell back to heuristic graphs."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from backend.api.exceptions import ApiError
from backend.graph.head_store import HeadStore
from backend.graph.store import GraphStore
from backend.repositories import run_async
from backend.schemas.paper import PaperStatus, PaperStatusData
from backend.services.paper_pipeline_scheduler import schedule_paper_pipeline

if TYPE_CHECKING:
    from backend.services.paper_service import PaperService

_REEXTRACT_QUEUED_MESSAGE = "已强制重新抽取，等待流水线启动…"


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


def _clear_persisted_artefacts(paper_id: str) -> None:
    """Remove final graph and refined head from disk."""
    GraphStore().delete(paper_id)
    HeadStore().delete(paper_id)


def _clear_in_memory_state(paper_service: PaperService, paper_id: str) -> None:
    """Reset preview and refined head caches for a paper."""
    paper_service._preview_graphs.pop(paper_id, None)
    paper_service._refined_head.pop(paper_id, None)
    paper_service._refined_classifier_input.pop(paper_id, None)


def force_reextract(paper_service: PaperService, paper_id: str) -> PaperStatusData:
    """Forcefully re-run the extraction pipeline for an existing paper.

    Clears graph/head artefacts, resets DB status to pending, bumps
    ``graph_version``, clears pipeline warnings, and re-schedules the pipeline
    from the stored PDF path.

    Raises:
        ApiError: 404 if paper does not exist (from caller).
        ApiError: 409 if it is already running.
        ApiError: 422 if the original PDF path is no longer available.
    """
    paper = run_async(paper_service._paper_repo.get(paper_id))
    if paper is None:
        raise ApiError("PAPER_NOT_FOUND", f"论文不存在: {paper_id}", status_code=404)

    if paper.status == PaperStatus.PROCESSING:
        raise ApiError(
            "PAPER_ALREADY_PROCESSING",
            f"论文 {paper_id} 正在处理中，请等待当前任务完成",
            status_code=409,
        )

    pdf_path_str = run_async(paper_service._paper_repo.get_pdf_path(paper_id))
    pdf_path = _resolve_pdf_path(pdf_path_str, paper_id)
    _clear_persisted_artefacts(paper_id)
    _clear_in_memory_state(paper_service, paper_id)

    run_async(paper_service._paper_repo.reset_for_reextract(paper_id))
    snapshot = run_async(
        paper_service._pipeline_repo.reset_for_reextract(
            paper_id,
            message=_REEXTRACT_QUEUED_MESSAGE,
        ),
    )

    schedule_paper_pipeline(paper_id, pdf_path)
    return snapshot
