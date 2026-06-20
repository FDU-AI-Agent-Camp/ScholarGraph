"""Paper routes — register here; business logic lives in services + BE modules."""

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from backend.api.deps import get_paper_service_dep, get_request_id
from backend.api.responses import paginated, success
from backend.api.sse import QA_STREAM_HEADERS, format_sse_event
from backend.graph.skeleton import build_skeleton_graph
from backend.schemas.paper import PaperStatus
from backend.schemas.paradigm import Paradigm
from backend.services.paper_service import PaperService

router = APIRouter(prefix="/papers")


class QaStreamRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)

    @field_validator("question")
    @classmethod
    def strip_and_require_non_empty(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            msg = "question must not be empty"
            raise ValueError(msg)
        return trimmed


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


@router.post("/{paper_id}/qa/stream")
async def stream_paper_qa(
    paper_id: str,
    body: QaStreamRequest,
    service: PaperService = Depends(get_paper_service_dep),
) -> StreamingResponse:
    """SSE multi-scale QA — delegates to BE-3 ``qa_stream()``."""

    await service.get_paper(paper_id)

    async def event_generator() -> AsyncIterator[str]:
        from backend.graph.qa import qa_stream

        async for evt in qa_stream(paper_id, body.question):
            yield format_sse_event(evt.event, evt.data)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=QA_STREAM_HEADERS,
    )
