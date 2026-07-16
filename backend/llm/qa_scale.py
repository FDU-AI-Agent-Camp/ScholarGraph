"""Backward-compatible re-exports — canonical router lives in ``backend.rag.qa_router``."""

from __future__ import annotations

from backend.rag.qa_router import (
    detect_cross_paper_intent,
    detect_question_scale,
    preferred_node_types,
)

__all__ = [
    "detect_cross_paper_intent",
    "detect_question_scale",
    "preferred_node_types",
]
