"""Question-scale routing for hybrid RAG (V2 §4.1).

Canonical enum: ``backend.rag.models.QuestionScale`` (``summary`` / ``detail`` / ``verification``).
Detection heuristics live in ``backend.llm.qa_scale`` (M2); this module is the stable import path
for HybridRetriever and benchmark wiring.
"""

from __future__ import annotations

from backend.llm.qa_scale import detect_question_scale, preferred_node_types
from backend.rag.models import QuestionScale, coerce_question_scale

__all__ = [
    "QuestionScale",
    "coerce_question_scale",
    "detect_question_scale",
    "preferred_node_types",
]
