# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Poll PaperService until async head refine completes or times out (§2.1 / P4)."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from backend.config import Settings, get_settings
from backend.ingest.router import IngestRouteKind, get_pdf_page_count, resolve_ingest_route
from backend.services.paper_service import get_paper_service

logger = logging.getLogger(__name__)

HEAD_REFINE_POLL_SECONDS = 0.5
PYMUPDF_ONLY_WAIT_SECONDS = 30.0
HEAD_REFINE_TIMEOUT_WARNING = "head_refine_timeout"


def resolve_head_refine_timeout_seconds(
    page_count: int,
    *,
    settings: Settings | None = None,
) -> float:
    """Map route to wait budget: short → MinerU, long → GROBID, pymupdf_only → brief."""
    cfg = settings or get_settings()
    route = resolve_ingest_route(page_count, settings=cfg)
    if route is None:
        return PYMUPDF_ONLY_WAIT_SECONDS
    if route == IngestRouteKind.SHORT:
        return float(cfg.ingest_mineru_timeout_seconds)
    return float(cfg.grobid_timeout_seconds)


async def wait_for_refined_classifier_input(
    paper_id: str,
    pdf_path: Path,
    fallback: str,
    *,
    settings: Settings | None = None,
) -> tuple[str, list[str]]:
    """
    Poll until ``apply_head_refine`` stores classifier input or timeout.

    Returns ``(classifier_input, warnings)``; on timeout uses ``fallback`` and
    appends ``head_refine_timeout``.
    """
    cfg = settings or get_settings()
    resolved = pdf_path.resolve()
    page_count = await asyncio.to_thread(get_pdf_page_count, resolved)
    timeout = resolve_head_refine_timeout_seconds(page_count, settings=cfg)
    paper_svc = get_paper_service()
    deadline = time.monotonic() + timeout
    warnings: list[str] = []

    while time.monotonic() < deadline:
        refined = paper_svc.get_refined_classifier_input(paper_id)
        if refined is not None:
            return refined, paper_svc.get_head_refine_warnings(paper_id)
        await asyncio.sleep(HEAD_REFINE_POLL_SECONDS)

    warnings.append(HEAD_REFINE_TIMEOUT_WARNING)
    logger.warning(
        "Head refine wait timed out for %s after %.0fs; using ingest snippets",
        paper_id,
        timeout,
    )
    return fallback, warnings
