"""FastAPI dependencies for QA scale verification (B4 / P2-1)."""

from __future__ import annotations

from fastapi import HTTPException

from backend.rag.models import QuestionScale
from backend.rag.qa_router import CROSS_PAPER_PATROL_GUIDE, detect_question_scale
from backend.schemas.qa_stream import QaStreamRequest


def verify_question_scale(paper_id: str, body: QaStreamRequest) -> QuestionScale:
    """Reject ``CROSS_PAPER`` questions before QA stream handling."""
    scale = detect_question_scale(
        body.question,
        current_paper_context={"paper_id": paper_id},
    )
    if scale == QuestionScale.CROSS_PAPER:
        raise HTTPException(status_code=400, detail=CROSS_PAPER_PATROL_GUIDE)
    return scale
