"""Ingest route selection by PDF page count (§2.1)."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

import fitz

from backend.config import Settings, get_settings
from backend.ingest.pdf import CLASSIFIER_HEAD_PAGE_LIMIT


class IngestRouteKind(StrEnum):
    SHORT = "short"
    LONG = "long"


def get_pdf_page_count(pdf_path: Path) -> int:
    """Return PDF page count via PyMuPDF."""
    resolved = pdf_path.resolve()
    with fitz.open(resolved) as document:
        return document.page_count


def resolve_ingest_route(
    page_count: int,
    *,
    settings: Settings | None = None,
) -> IngestRouteKind | None:
    """
    Resolve path-B backend for head refinement.

    Returns None when ``INGEST_ROUTE=pymupdf_only`` (skip async path B).
    """
    cfg = settings or get_settings()
    if cfg.ingest_route == "pymupdf_only":
        return None
    limit = cfg.ingest_short_page_limit
    if page_count <= limit:
        return IngestRouteKind.SHORT
    return IngestRouteKind.LONG


def is_short_pdf(page_count: int, *, settings: Settings | None = None) -> bool:
    cfg = settings or get_settings()
    return page_count <= cfg.ingest_short_page_limit


def ingest_page_limit_default() -> int:
    """Documented alias aligned with classifier head scan."""
    return CLASSIFIER_HEAD_PAGE_LIMIT
