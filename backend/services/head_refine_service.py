"""Async path-B ingest + head merge after upload (§2.1, non-blocking)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path

from backend.config import Settings, get_settings
from backend.ingest.grobid_client import fetch_grobid_tei
from backend.ingest.head_candidates import HeadCandidate, build_pymupdf_head_candidate
from backend.ingest.mineru_backend import run_mineru_pipeline
from backend.ingest.pdf import extract_pdf_text
from backend.ingest.router import IngestRouteKind, get_pdf_page_count, is_short_pdf, resolve_ingest_route
from backend.ingest.snippets import extract_conclusion_tail, extract_meta_info
from backend.ingest.tei_parser import parse_tei_to_head_candidate
from backend.schemas.ingest_head import IngestHead
from backend.services.head_merge_service import get_head_merge_service

logger = logging.getLogger(__name__)


def _enrich_with_full_text_signals(merged: IngestHead, full_text: str) -> IngestHead:
    """Fill missing conclusion / journal / funding / affiliation from full-text regex heuristics."""
    update: dict[str, str] = {}

    if not merged.conclusion.strip():
        conclusion = extract_conclusion_tail(full_text)
        if conclusion:
            update["conclusion"] = conclusion

    meta = extract_meta_info(full_text)
    for meta_field in ("journal", "funding", "affiliation"):
        if not getattr(merged, meta_field).strip() and meta.get(meta_field, "").strip():
            update[meta_field] = meta[meta_field].strip()

    if not update:
        return merged
    return merged.model_copy(update=update)


@dataclass
class HeadRefineResult:
    """Outcome of async head refinement (never fails the main pipeline)."""

    paper_id: str
    page_count: int
    route: IngestRouteKind | None
    merged: IngestHead
    classifier_input: str
    warnings: list[str] = field(default_factory=list)


async def _fetch_path_b_candidate(
    pdf_path: Path,
    route: IngestRouteKind,
    *,
    settings: Settings,
) -> tuple[HeadCandidate | None, list[str]]:
    warnings: list[str] = []
    if route == IngestRouteKind.SHORT:
        if not settings.ingest_mineru_enabled:
            warnings.append("mineru_disabled")
            return None, warnings
        candidate = await asyncio.to_thread(run_mineru_pipeline, pdf_path, settings=settings)
        if candidate is None:
            warnings.append("mineru_unavailable")
        return candidate, warnings

    tei = await fetch_grobid_tei(pdf_path, settings=settings)
    if not tei:
        warnings.append("grobid_unavailable")
        return None, warnings
    try:
        return parse_tei_to_head_candidate(tei), warnings
    except Exception:
        logger.exception("TEI parse failed for %s", pdf_path.name)
        warnings.append("tei_parse_failed")
        return None, warnings


async def refine_head_async(
    paper_id: str,
    pdf_path: Path,
    *,
    settings: Settings | None = None,
) -> HeadRefineResult:
    """
    Run async path B + head merge without raising to the caller.

    Sync upload already produced PyMuPDF ``full_text`` and initial ``classifier_input``.
    """
    cfg = settings or get_settings()
    resolved = pdf_path.resolve()
    page_count = await asyncio.to_thread(get_pdf_page_count, resolved)
    route = resolve_ingest_route(page_count, settings=cfg)
    warnings: list[str] = []

    try:
        snippets = await asyncio.to_thread(build_pymupdf_head_candidate, resolved)
    except Exception:
        logger.exception("PyMuPDF head candidate failed for %s", paper_id)
        snippets = HeadCandidate(source="pymupdf")
        warnings.append("pymupdf_head_failed")

    path_b: HeadCandidate | None = None
    if route is not None:
        path_b, path_warnings = await _fetch_path_b_candidate(resolved, route, settings=cfg)
        warnings.extend(path_warnings)
    else:
        warnings.append("route_pymupdf_only")

    merged = await get_head_merge_service().merge(
        snippets,
        path_b,
        is_short=is_short_pdf(page_count, settings=cfg),
    )

    # Enrich merged head with meta-information and conclusion extracted from full text.
    # Head-only extraction misses the conclusion and sometimes drops meta signals; this
    # is a low-cost regex pass that fills gaps without re-merging via LLM.
    try:
        full_text = await asyncio.to_thread(extract_pdf_text, resolved)
    except Exception:
        logger.exception("Full-text extraction failed for meta enrichment %s", paper_id)
        full_text = ""

    if full_text:
        merged = _enrich_with_full_text_signals(merged, full_text)

    classifier_input = merged.to_classifier_input()
    if not classifier_input.strip():
        classifier_input = snippets.title or ""

    from backend.services.paper_service import get_paper_service

    get_paper_service().apply_head_refine(
        paper_id,
        merged=merged,
        classifier_input=classifier_input,
        warnings=warnings,
    )

    return HeadRefineResult(
        paper_id=paper_id,
        page_count=page_count,
        route=route,
        merged=merged,
        classifier_input=classifier_input,
        warnings=warnings,
    )
