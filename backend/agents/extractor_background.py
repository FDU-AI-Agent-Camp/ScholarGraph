# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Background extraction orchestration (Slice 2).

Provides the entry point for long papers: emit MVP preview synchronously, then
schedule the full chunked extraction as a background task running under RPM/TPM
rate limiting.
"""

from __future__ import annotations

import logging

from backend.agents.extract_types import ExtractResult
from backend.agents.extractor import (
    MVP_SKELETON_PREVIEW_CODE,
    _extract_mvp,
    _resolve_head_context,
    _save_preview_graph,
    _to_unified_graph,
    extract_title,
)
from backend.config import Settings, get_settings
from backend.schemas.graph import GraphNode, NodeType, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm, ParadigmClassification

logger = logging.getLogger(__name__)


def should_run_background_extraction(full_text: str, settings: Settings) -> bool:
    """Long papers in live mode should be extracted in the background."""
    if settings.is_llm_mock:
        return False
    if not settings.extract_chunked_enabled:
        return False
    return len(full_text) > settings.extract_max_input_chars


def _minimal_pending_graph(paper_id: str, title: str | None, paradigm: Paradigm) -> UnifiedPaperGraph:
    """Return a valid placeholder graph while background extraction runs."""
    node_type = NodeType.THESIS if paradigm == Paradigm.HSS else NodeType.RESEARCH_QUESTION
    return UnifiedPaperGraph(
        paper_id=paper_id,
        title=title,
        paradigm=paradigm,
        nodes=[GraphNode(id="pending", label="后台全量抽取中", type=node_type)],
        edges=[],
        summary=f"全量抽取已在后台启动: {paper_id}",
    )


async def extract_preview_and_schedule_full(
    full_text: str,
    paradigm: Paradigm,
    *,
    paper_id: str,
    classification: ParadigmClassification,
    settings: Settings | None = None,
    pipeline_generation_id: str | None = None,
) -> ExtractResult:
    """Emit MVP preview synchronously, then schedule full extraction in background.

    This is the Slice 2 entry point for long papers: the frontend receives a
    preview within seconds while the heavy chunked extraction runs offline under
    RPM/TPM rate limiting.
    """
    cfg = settings or get_settings()
    title = extract_title(full_text)
    head_context = await _resolve_head_context(paper_id)

    try:
        mvp_extracted = await _extract_mvp(
            full_text,
            paradigm,
            paper_id=paper_id,
            title=title,
            head_context=head_context,
            settings=cfg,
        )
        preview_graph = _to_unified_graph(mvp_extracted, paper_id=paper_id, paradigm=paradigm)
        await _save_preview_graph(paper_id, preview_graph, warnings=[MVP_SKELETON_PREVIEW_CODE])
    except Exception as exc:
        logger.warning("mvp_extraction_failed", extra={"paper_id": paper_id, "reason": str(exc)})
        preview_graph = None

    from backend.services.extract_worker import schedule_full_extraction

    schedule_full_extraction(
        paper_id,
        full_text,
        paradigm,
        classification,
        head_context=head_context,
        settings=cfg,
        pipeline_generation_id=pipeline_generation_id,
    )

    if preview_graph is not None:
        return ExtractResult(graph=preview_graph, warnings=[MVP_SKELETON_PREVIEW_CODE])

    return ExtractResult(
        graph=_minimal_pending_graph(paper_id, title, paradigm),
        warnings=[MVP_SKELETON_PREVIEW_CODE],
    )
