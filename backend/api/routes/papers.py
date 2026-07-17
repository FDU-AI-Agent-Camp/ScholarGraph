# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Paper routes — register here; business logic lives in services + BE modules."""

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse

from backend.api.deps import get_hybrid_retriever_dep, get_paper_service_dep, get_request_id
from backend.api.qa_deps import verify_question_scale
from backend.api.responses import paginated, success
from backend.api.sse import QA_STREAM_HEADERS, format_sse_event
from backend.graph.skeleton import build_skeleton_graph
from backend.rag.hybrid_retriever import HybridRetriever
from backend.rag.models import QuestionScale
from backend.schemas.paper import PaperStatus
from backend.schemas.paradigm import Paradigm
from backend.schemas.qa_stream import QaStreamRequest
from backend.services.paper_service import PaperService
from backend.services.qa_retrieval import build_retrieval_context_with_fallback

router = APIRouter(prefix="/papers")


@router.get("")
async def list_papers(
    paradigm: Paradigm | None = None,
    status: PaperStatus | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    request_id: str = Depends(get_request_id),
    service: PaperService = Depends(get_paper_service_dep),
) -> dict:
    """List papers with optional paradigm/status filters and pagination."""
    items, total = await service.list_papers(
        paradigm=paradigm,
        status=status,
        offset=offset,
        limit=limit,
    )
    return paginated(items, total=total, offset=offset, limit=limit, request_id=request_id)


@router.post("", status_code=201)
async def create_paper(
    file: UploadFile = File(...),
    request_id: str = Depends(get_request_id),
    service: PaperService = Depends(get_paper_service_dep),
) -> dict:
    """Upload a PDF; returns pending paper_id and schedules the ingest pipeline."""
    content = await file.read()
    result = await service.create_from_upload(
        filename=file.filename or "upload.pdf",
        content=content,
    )
    return success(result, request_id)


@router.get("/{paper_id}")
async def get_paper(
    paper_id: str,
    request_id: str = Depends(get_request_id),
    service: PaperService = Depends(get_paper_service_dep),
) -> dict:
    """Return paper metadata by id."""
    paper = await service.get_paper(paper_id)
    return success(paper, request_id)


@router.get("/{paper_id}/status")
async def get_paper_status(
    paper_id: str,
    request_id: str = Depends(get_request_id),
    service: PaperService = Depends(get_paper_service_dep),
) -> dict:
    """Return pipeline progress snapshot for long-polling."""
    status_data = await service.get_status(paper_id)
    return success(status_data, request_id)


@router.get("/{paper_id}/graph")
async def get_paper_graph(
    paper_id: str,
    view: str | None = Query(default=None, description="Use 'skeleton' for downsampled graph"),
    request_id: str = Depends(get_request_id),
    service: PaperService = Depends(get_paper_service_dep),
) -> dict:
    """Return UnifiedPaperGraph when paper status is ready.

    Query ``?view=skeleton`` returns only the largest connected component,
    capped at 300 nodes by degree centrality.
    """
    graph = await service.get_graph(paper_id)
    if view == "skeleton":
        graph = build_skeleton_graph(graph)
    return success(graph, request_id)


@router.delete("/{paper_id}", status_code=204)
async def delete_paper(
    paper_id: str,
    force: bool = Query(
        default=False,
        description="When true, cancel in-flight PROCESSING/INDEXING work then cascade-delete",
    ),
    service: PaperService = Depends(get_paper_service_dep),
) -> None:
    """Cascading physical delete: tasks → Chroma → graph/head JSON → PDF → SQL.

    Default blocks ``PROCESSING`` / ``INDEXING`` with 409; ``force=true`` aborts first.
    """
    await service.delete_paper(paper_id, force=force)


@router.post("/{paper_id}/reextract")
async def force_reextract_paper(
    paper_id: str,
    force: bool = Query(
        default=False,
        description="When true, cancel in-flight PROCESSING work then re-queue",
    ),
    request_id: str = Depends(get_request_id),
    service: PaperService = Depends(get_paper_service_dep),
) -> dict:
    """Forcefully re-run the extraction pipeline for an existing paper.

    This is the escape hatch when the previous extraction fell back to a
    heuristic graph (e.g. ``extract_llm_timeout``). It clears the existing
    graph, preview, warnings and refined head, resets status to PENDING and
    re-enqueues the pipeline from the stored PDF.

    Default blocks ``PROCESSING`` / ``INDEXING`` with 409; pass ``force=true``
    to abort and restart.
    """
    status_data = await service.force_reextract(paper_id, force=force)
    return success(status_data, request_id)


@router.post("/{paper_id}/qa/stream")
async def stream_paper_qa(
    paper_id: str,
    body: QaStreamRequest,
    service: PaperService = Depends(get_paper_service_dep),
    retriever: HybridRetriever = Depends(get_hybrid_retriever_dep),
    _scale: QuestionScale = Depends(verify_question_scale),
) -> StreamingResponse:
    """SSE multi-scale QA — HybridRetriever → RetrievalContext → ``qa_stream()``."""

    await service.get_paper(paper_id)

    retrieval_result = await build_retrieval_context_with_fallback(
        paper_id,
        body.question,
        retriever=retriever,
        paper_service=service,
        top_k=body.top_k,
    )

    async def event_generator() -> AsyncIterator[str]:
        from backend.graph.qa import qa_stream

        if retrieval_result.warning_event is not None:
            yield format_sse_event("warning", retrieval_result.warning_event)

        async for evt in qa_stream(
            paper_id,
            body.question,
            retrieval_context=retrieval_result.context,
            retrieval_warning=retrieval_result.warning_event,
        ):
            yield format_sse_event(evt.event, evt.data)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=QA_STREAM_HEADERS,
    )
