"""Paper graph extractor — LLM structured output with heuristic fallback (Phase F)."""

from __future__ import annotations

import logging

from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE
from backend.agents.extract_heuristic import build_heuristic_graph, extract_title
from backend.agents.extract_llm import extract_with_llm
from backend.agents.extract_types import ExtractResult
from backend.agents.mock_agents import mock_extract
from backend.config import Settings, get_settings
from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm
from backend.services.errors import PIPELINE_FAILED_CODE, ServiceError

logger = logging.getLogger(__name__)


def _resolve_head_context(paper_id: str) -> str | None:
    from backend.services.paper_service import get_paper_service

    head = get_paper_service().get_refined_head(paper_id)
    if head is None:
        return None
    parts = [head.title.strip(), head.abstract.strip(), head.intro.strip()]
    merged = "\n\n".join(part for part in parts if part)
    return merged or None


async def _extract_live(
    full_text: str,
    paradigm: Paradigm,
    *,
    paper_id: str,
    settings: Settings,
) -> ExtractResult:
    title = extract_title(full_text)
    head_context = _resolve_head_context(paper_id)

    if not settings.extract_llm_enabled:
        logger.warning(
            "extract_llm_disabled",
            extra={"paper_id": paper_id, "paradigm": paradigm.value},
        )
        return ExtractResult(
            graph=build_heuristic_graph(full_text, paradigm, title=title).model_copy(
                update={"paper_id": paper_id, "paradigm": paradigm},
            ),
            warnings=[EXTRACT_HEURISTIC_FALLBACK_CODE],
        )

    try:
        graph = await extract_with_llm(
            full_text,
            paradigm,
            paper_id=paper_id,
            title=title,
            head_context=head_context,
            settings=settings,
        )
        return ExtractResult(
            graph=graph.model_copy(update={"paper_id": paper_id, "paradigm": paradigm}),
            warnings=[],
        )
    except Exception as exc:
        if not settings.extract_heuristic_fallback:
            raise ServiceError(PIPELINE_FAILED_CODE, f"图谱 LLM 抽取失败: {exc}") from exc

        logger.warning(
            "extract_llm_fallback",
            extra={"paper_id": paper_id, "paradigm": paradigm.value, "reason": str(exc)},
        )
        graph = build_heuristic_graph(full_text, paradigm, title=title).model_copy(
            update={"paper_id": paper_id, "paradigm": paradigm},
        )
        return ExtractResult(graph=graph, warnings=[EXTRACT_HEURISTIC_FALLBACK_CODE])


async def extract(
    full_text: str,
    paradigm: Paradigm,
    *,
    paper_id: str | None = None,
) -> ExtractResult:
    """Extract a validated graph; live mode prefers LLM with heuristic fallback."""
    settings = get_settings()
    if settings.is_llm_mock:
        graph = mock_extract(full_text, paradigm)
        if paper_id:
            graph = graph.model_copy(update={"paper_id": paper_id, "paradigm": paradigm})
        return ExtractResult(graph=graph, warnings=[])

    if not full_text or not full_text.strip():
        raise ValueError("full_text must be a non-empty string.")

    normalized_paradigm = Paradigm(paradigm)
    resolved_paper_id = paper_id or "paper-unknown"
    return await _extract_live(
        full_text,
        normalized_paradigm,
        paper_id=resolved_paper_id,
        settings=settings,
    )


async def extract_graph_only(full_text: str, paradigm: Paradigm, *, paper_id: str | None = None) -> UnifiedPaperGraph:
    """Backward-compatible helper returning only the graph payload."""
    return (await extract(full_text, paradigm, paper_id=paper_id)).graph
