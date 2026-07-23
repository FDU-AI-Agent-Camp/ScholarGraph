# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Paper graph extractor — LLM structured output with heuristic fallback (Phase F)."""

from __future__ import annotations

import logging

from backend.agents.extract_constants import (
    EXTRACT_HEURISTIC_FALLBACK_CODE,
    MVP_SKELETON_PREVIEW_CODE,
)
from backend.agents.extract_edges import build_edges_with_llm
from backend.agents.extract_heuristic import build_heuristic_graph, extract_title
from backend.agents.extract_llm import extract_with_llm
from backend.agents.extract_nodes import extract_nodes_with_llm
from backend.agents.extract_retry import (
    _RETRY_CONFIG,
    extract_chunked_with_retry,
    handle_extract_failure,
    run_extract_subgraph_with_retry,
    warning_code_for_error,
)
from backend.agents.extract_types import ExtractResult
from backend.agents.mock_agents import mock_extract
from backend.config import Settings, get_settings
from backend.schemas.extract_phase import ExtractedGraph
from backend.schemas.graph import GraphEdge, GraphNode, NodeType, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm
from backend.services.paper_service import PaperService

logger = logging.getLogger(__name__)

MVP_MIN_INPUT_CHARS = 1500
MVP_TARGET_INPUT_CHARS = 3000

# Re-export for backward-compatible tests that import the helper from here.
_handle_extract_failure = handle_extract_failure


def _fallback_to_heuristic(
    full_text: str,
    paradigm: Paradigm,
    *,
    paper_id: str,
    title: str,
    reason: BaseException | str,
) -> ExtractResult:
    """Degrade to ``build_heuristic_graph`` and record fallback warnings.

    Warnings always include the coarse-grained ``EXTRACT_HEURISTIC_FALLBACK_CODE``
    for backward compatibility. When the failure reason can be mapped to a
    fine-grained machine code (timeout, rate limit, JSON parse, schema
    validation, context window), that code is emitted first so observers can
    distinguish root causes without parsing the fallback message.
    """
    specific_code = warning_code_for_error(reason)
    warnings = (
        [specific_code, EXTRACT_HEURISTIC_FALLBACK_CODE]
        if specific_code != EXTRACT_HEURISTIC_FALLBACK_CODE
        else [EXTRACT_HEURISTIC_FALLBACK_CODE]
    )
    logger.warning(
        "extract_llm_fallback",
        extra={"paper_id": paper_id, "warning_codes": warnings, "reason": str(reason)},
    )
    graph = build_heuristic_graph(full_text, paradigm, title=title).model_copy(
        update={"paper_id": paper_id, "paradigm": paradigm},
    )
    return ExtractResult(graph=graph, warnings=warnings)


async def _resolve_head_context(
    paper_id: str,
    *,
    paper_service: PaperService | None = None,
) -> str | None:
    """Build optional document-head prefix from in-memory refine or ``HeadStore`` (X6)."""
    from backend.graph.head_store import HeadStore
    from backend.services.paper_service import get_paper_service

    service = paper_service or get_paper_service()
    head = await service.get_refined_head(paper_id)
    if head is None:
        record = HeadStore().load(paper_id)
        head = record.merged if record is not None else None
    if head is None:
        return None
    parts = [head.title.strip(), head.abstract.strip(), head.intro.strip()]
    merged = "\n\n".join(part for part in parts if part)
    return merged or None


def _build_mvp_input(full_text: str, head_context: str | None) -> str:
    """Compose the golden input for MVP skeleton extraction.

    Priority: refined document head (title/abstract/intro), then a trailing
    conclusion slice, then the beginning of the full text. The result is
    capped around ``MVP_TARGET_INPUT_CHARS`` so a single LLM call can finish
    within the synchronous-ish budget.
    """
    parts: list[str] = []
    if head_context and head_context.strip():
        parts.append(head_context.strip())

    remaining_budget = max(MVP_TARGET_INPUT_CHARS - sum(len(p) for p in parts), 0)
    if remaining_budget > MVP_MIN_INPUT_CHARS:
        # Try to grab a conclusion/discussion slice from the tail of the paper.
        tail = full_text[-remaining_budget:] if len(full_text) > remaining_budget else full_text
        # Stop at a paragraph boundary when possible to avoid cutting sentences.
        if len(tail) > MVP_MIN_INPUT_CHARS and "\n\n" in tail:
            tail = tail[tail.index("\n\n") + 2 :]
        if tail.strip():
            parts.append(tail.strip())

    if sum(len(p) for p in parts) < MVP_MIN_INPUT_CHARS:
        # Fall back to the paper beginning if head is too short.
        leading = full_text[:MVP_TARGET_INPUT_CHARS]
        if leading.strip() and leading.strip() not in parts:
            parts.append(leading.strip())

    return "\n\n".join(parts)


def _to_unified_graph(
    extracted: ExtractedGraph,
    *,
    paper_id: str,
    paradigm: Paradigm,
) -> UnifiedPaperGraph:
    """Convert an ``ExtractedGraph`` to the public ``UnifiedPaperGraph`` schema."""
    return UnifiedPaperGraph(
        paper_id=paper_id,
        title=extracted.title,
        paradigm=paradigm,
        nodes=[GraphNode(id=n.id, label=n.label, type=NodeType(n.type), data=n.data) for n in extracted.nodes],
        edges=[
            GraphEdge(
                id=e.id,
                source=e.source,
                target=e.target,
                label=e.label,
                type=e.type,
                rationale=e.rationale,
                source_span=e.source_span,
                confidence=e.confidence,
                data=e.data,
            )
            for e in extracted.edges
        ],
        summary=extracted.summary,
    )


async def _save_preview_graph(
    paper_id: str,
    graph: UnifiedPaperGraph,
    *,
    warnings: list[str] | None = None,
    paper_service: PaperService | None = None,
) -> None:
    """Persist a graph as the current preview and surface it on status/detail.

    Preview saving is best-effort: unit tests may call ``extract()`` with
    unregistered paper_ids, in which case we simply skip the preview update.
    """
    from backend.services.paper_service import get_paper_service
    from backend.services.paper_warning_service import WarningType, get_paper_warning_service

    service = paper_service or get_paper_service()
    try:
        await service.ensure_paper_exists(paper_id)
    except Exception:
        logger.debug(
            "skip_preview_for_unregistered_paper",
            extra={"paper_id": paper_id},
        )
        return
    await service.save_preview_graph(paper_id, graph)
    await service.mark_preview_available(paper_id)
    if warnings:
        await get_paper_warning_service().record(paper_id, WarningType.EXTRACT, warnings)


async def _extract_mvp(
    full_text: str,
    paradigm: Paradigm,
    *,
    paper_id: str,
    title: str,
    head_context: str | None,
    settings: Settings,
) -> ExtractedGraph:
    """Extract a lightweight MVP skeleton graph from the document head + tail.

    This path deliberately avoids chunking and uses a single node + edge pass
    so the frontend can display a preview within seconds.
    """
    mvp_input = _build_mvp_input(full_text, head_context)
    node_list = await extract_nodes_with_llm(
        mvp_input,
        paradigm,
        paper_id=paper_id,
        title=title,
        head_context=head_context,
        settings=settings,
    )
    edge_list = await build_edges_with_llm(
        node_list,
        mvp_input,
        paper_id=paper_id,
        title=title,
        head_context=head_context,
        settings=settings,
    )
    return ExtractedGraph(
        paper_id=paper_id,
        title=title,
        paradigm=paradigm,
        nodes=list(node_list.nodes),
        edges=list(edge_list.edges),
        summary=f"MVP skeleton preview for {paper_id}",
        warnings=[MVP_SKELETON_PREVIEW_CODE],
    )


async def _extract_live(
    full_text: str,
    paradigm: Paradigm,
    *,
    paper_id: str,
    settings: Settings,
) -> ExtractResult:
    title = extract_title(full_text)
    head_context = await _resolve_head_context(paper_id)

    if not settings.extract_llm_enabled:
        logger.warning(
            "extract_llm_disabled",
            extra={"paper_id": paper_id, "paradigm": paradigm.value},
        )
        return _fallback_to_heuristic(
            full_text,
            paradigm,
            paper_id=paper_id,
            title=title,
            reason="extract_llm_disabled",
        )

    if not settings.extract_two_phase_enabled:
        return await _extract_single_phase(
            full_text,
            paradigm,
            paper_id=paper_id,
            title=title,
            head_context=head_context,
            settings=settings,
        )

    return await _extract_two_phase(
        full_text,
        paradigm,
        paper_id=paper_id,
        title=title,
        head_context=head_context,
        settings=settings,
    )


async def _extract_single_phase(
    full_text: str,
    paradigm: Paradigm,
    *,
    paper_id: str,
    title: str,
    head_context: str | None,
    settings: Settings,
) -> ExtractResult:
    """Legacy single-phase extraction path (kept for backward compatibility).

    ``extract_with_llm`` is invoked through a tenacity retry wrapper so transient
    failures (timeouts, rate limits) are retried before falling back.
    """
    from tenacity import retry

    @retry(**_RETRY_CONFIG)
    async def _call_extract_with_llm() -> UnifiedPaperGraph:
        return await extract_with_llm(
            full_text,
            paradigm,
            paper_id=paper_id,
            title=title,
            head_context=head_context,
            settings=settings,
        )

    try:
        graph = await _call_extract_with_llm()
    except Exception as exc:
        return handle_extract_failure(
            exc,
            settings=settings,
            paper_id=paper_id,
            fallback_action=lambda reason: _fallback_to_heuristic(
                full_text,
                paradigm,
                paper_id=paper_id,
                title=title,
                reason=reason,
            ),
        )

    final_graph = graph.model_copy(update={"paper_id": paper_id, "paradigm": paradigm})
    await _save_preview_graph(paper_id, final_graph, warnings=[])
    return ExtractResult(graph=final_graph, warnings=[])


async def _extract_chunked_two_phase(
    full_text: str,
    paradigm: Paradigm,
    *,
    paper_id: str,
    title: str,
    head_context: str | None,
    settings: Settings,
) -> ExtractResult:
    """Chunked two-phase extraction for papers longer than the input limit.

    Transient failures (timeouts, rate limits) are retried with exponential
    backoff by tenacity. Deterministic failures trigger heuristic fallback.
    """
    try:
        extracted_graph = await extract_chunked_with_retry(
            full_text,
            paradigm,
            paper_id=paper_id,
            title=title,
            head_context=head_context,
            settings=settings,
        )
    except Exception as exc:
        return handle_extract_failure(
            exc,
            settings=settings,
            paper_id=paper_id,
            fallback_action=lambda reason: _fallback_to_heuristic(
                full_text,
                paradigm,
                paper_id=paper_id,
                title=title,
                reason=reason,
            ),
        )

    unified = UnifiedPaperGraph(
        paper_id=paper_id,
        title=title,
        paradigm=paradigm,
        nodes=[GraphNode(id=n.id, label=n.label, type=NodeType(n.type), data=n.data) for n in extracted_graph.nodes],
        edges=[
            GraphEdge(
                id=e.id,
                source=e.source,
                target=e.target,
                label=e.label,
                type=e.type,
                rationale=e.rationale,
                source_span=e.source_span,
                confidence=e.confidence,
                data=e.data,
            )
            for e in extracted_graph.edges
        ],
        summary=extracted_graph.summary,
    )
    await _save_preview_graph(paper_id, unified, warnings=extracted_graph.warnings)
    return ExtractResult(graph=unified, warnings=extracted_graph.warnings)


async def _extract_two_phase(
    full_text: str,
    paradigm: Paradigm,
    *,
    paper_id: str,
    title: str,
    head_context: str | None,
    settings: Settings,
) -> ExtractResult:
    """Two-phase extraction with self-repair via LangGraph sub-graph.

    For long papers this method first emits an MVP skeleton preview so the
    frontend can start QA while the full chunked extraction continues.
    """
    if len(full_text) > settings.extract_max_input_chars and settings.extract_chunked_enabled:
        # Long paper: ship an MVP preview immediately, then do the heavy work.
        try:
            mvp_extracted = await _extract_mvp(
                full_text,
                paradigm,
                paper_id=paper_id,
                title=title,
                head_context=head_context,
                settings=settings,
            )
        except Exception as exc:
            logger.warning(
                "mvp_extraction_failed",
                extra={"paper_id": paper_id, "reason": str(exc)},
            )
            # Do not block the full extraction just because the MVP preview failed.
            mvp_extracted = None

        if mvp_extracted is not None:
            await _save_preview_graph(
                paper_id,
                _to_unified_graph(mvp_extracted, paper_id=paper_id, paradigm=paradigm),
                warnings=[MVP_SKELETON_PREVIEW_CODE],
            )

        return await _extract_chunked_two_phase(
            full_text,
            paradigm,
            paper_id=paper_id,
            title=title,
            head_context=head_context,
            settings=settings,
        )

    # Short paper: full extraction is fast enough to serve as its own preview.
    try:
        result = await run_extract_subgraph_with_retry(
            full_text,
            paradigm,
            paper_id=paper_id,
            title=title,
            head_context=head_context,
        )
        final_graph = result.graph.model_copy(update={"paper_id": paper_id, "paradigm": paradigm})
        await _save_preview_graph(paper_id, final_graph, warnings=result.warnings)
        return ExtractResult(graph=final_graph, warnings=result.warnings)
    except Exception as exc:
        return handle_extract_failure(
            exc,
            settings=settings,
            paper_id=paper_id,
            fallback_action=lambda reason: _fallback_to_heuristic(
                full_text,
                paradigm,
                paper_id=paper_id,
                title=title,
                reason=reason,
            ),
        )


async def extract(
    full_text: str,
    paradigm: Paradigm,
    *,
    paper_id: str | None = None,
) -> ExtractResult:
    """Extract a validated graph; live mode prefers LLM with heuristic fallback."""
    settings = get_settings()
    resolved_paper_id = paper_id or "paper-unknown"
    normalized_paradigm = Paradigm(paradigm)

    if settings.is_llm_mock:
        graph = mock_extract(full_text, normalized_paradigm)
        graph = graph.model_copy(update={"paper_id": resolved_paper_id, "paradigm": normalized_paradigm})
        await _save_preview_graph(resolved_paper_id, graph, warnings=[])
        return ExtractResult(graph=graph, warnings=[])

    if not full_text or not full_text.strip():
        raise ValueError("full_text must be a non-empty string.")

    return await _extract_live(
        full_text,
        normalized_paradigm,
        paper_id=resolved_paper_id,
        settings=settings,
    )


async def extract_graph_only(full_text: str, paradigm: Paradigm, *, paper_id: str | None = None) -> UnifiedPaperGraph:
    """Backward-compatible helper returning only the graph payload."""
    return (await extract(full_text, paradigm, paper_id=paper_id)).graph
