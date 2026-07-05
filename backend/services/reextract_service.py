"""Force re-extract escape hatch for papers that fell back to heuristic graphs."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from backend.api.exceptions import ApiError
from backend.graph.head_store import HeadStore
from backend.graph.store import GraphStore
from backend.schemas.paper import PaperStatus, PaperStatusData
from backend.services.paper_pipeline_scheduler import schedule_paper_pipeline

if TYPE_CHECKING:
    from backend.services.paper_service import PaperService


_REEXTRACT_QUEUED_MESSAGE = "已强制重新抽取，等待流水线启动…"


def _resolve_pdf_path(paper_service: PaperService, paper_id: str) -> Path:
    """Return the stored PDF path or raise a 422 error if it is missing."""
    pdf_path = paper_service._pdf_paths.get(paper_id)
    if pdf_path is not None and pdf_path.is_file():
        return pdf_path

    raise ApiError(
        "PDF_NOT_FOUND",
        f"无法找到论文 {paper_id} 的原始 PDF，无法重新抽取",
        status_code=422,
    )


def _clear_persisted_artefacts(paper_id: str) -> None:
    """Remove final graph and refined head from disk."""
    GraphStore().delete(paper_id)
    HeadStore().delete(paper_id)


def _clear_in_memory_state(paper_service: PaperService, paper_id: str) -> None:
    """Reset preview, warnings and refined head caches for a paper."""
    paper_service._preview_graphs.pop(paper_id, None)
    paper_service._preview_available.pop(paper_id, None)
    paper_service._extract_warnings.pop(paper_id, None)
    paper_service._classify_warnings.pop(paper_id, None)
    paper_service._head_refine_warnings.pop(paper_id, None)
    paper_service._refined_head.pop(paper_id, None)
    paper_service._refined_classifier_input.pop(paper_id, None)


def force_reextract(paper_service: PaperService, paper_id: str) -> PaperStatusData:
    """Forcefully re-run the extraction pipeline for an existing paper.

    This is the escape hatch for users who see an LLM-timeout fallback.
    The existing graph, preview, warnings and refined head are cleared,
    the paper status is reset to PENDING/PROCESSING, and the pipeline is
    re-scheduled from the stored PDF path.

    Raises:
        ApiError: 404 if paper does not exist (from caller).
        ApiError: 409 if it is already running.
        ApiError: 422 if the original PDF path is no longer available.
    """
    paper = paper_service._papers[paper_id]

    if paper.status == PaperStatus.PROCESSING:
        raise ApiError(
            "PAPER_ALREADY_PROCESSING",
            f"论文 {paper_id} 正在处理中，请等待当前任务完成",
            status_code=409,
        )

    pdf_path = _resolve_pdf_path(paper_service, paper_id)
    _clear_persisted_artefacts(paper_id)
    _clear_in_memory_state(paper_service, paper_id)

    now = datetime.now(UTC)
    paper_service._papers[paper_id] = paper.model_copy(
        update={
            "status": PaperStatus.PENDING,
            "paradigm": None,
            "classification": None,
            "preview_available": False,
            "updated_at": now,
        },
    )
    paper_service._status[paper_id] = PaperStatusData(
        paper_id=paper_id,
        status=PaperStatus.PENDING,
        percent=0,
        stage=None,
        message=_REEXTRACT_QUEUED_MESSAGE,
        updated_at=now,
    )

    schedule_paper_pipeline(paper_id, pdf_path)
    return paper_service._status[paper_id]
