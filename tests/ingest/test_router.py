"""Ingest route selection by page count."""

from __future__ import annotations

from pathlib import Path

import pytest
from backend.config import Settings
from backend.ingest.router import (
    IngestRouteKind,
    get_pdf_page_count,
    ingest_page_limit_default,
    is_short_pdf,
    resolve_ingest_route,
)


def test_ingest_page_limit_default_matches_classifier() -> None:
    assert ingest_page_limit_default() == 25


def test_resolve_ingest_route_short_at_boundary() -> None:
    settings = Settings(_env_file=None, ingest_route="auto", ingest_short_page_limit=25)
    assert resolve_ingest_route(25, settings=settings) == IngestRouteKind.SHORT
    assert resolve_ingest_route(26, settings=settings) == IngestRouteKind.LONG


def test_resolve_ingest_route_pymupdf_only_returns_none() -> None:
    settings = Settings(_env_file=None, ingest_route="pymupdf_only")
    assert resolve_ingest_route(10, settings=settings) is None


def test_is_short_pdf_respects_limit() -> None:
    settings = Settings(_env_file=None, ingest_short_page_limit=25)
    assert is_short_pdf(25, settings=settings) is True
    assert is_short_pdf(26, settings=settings) is False


def test_get_pdf_page_count(structured_stem_pdf: Path) -> None:
    assert get_pdf_page_count(structured_stem_pdf) >= 1


@pytest.mark.parametrize(
    ("page_count", "expected"),
    [(1, IngestRouteKind.SHORT), (100, IngestRouteKind.LONG)],
)
def test_resolve_ingest_route_auto(page_count: int, expected: IngestRouteKind) -> None:
    settings = Settings(_env_file=None, ingest_route="auto", ingest_short_page_limit=25)
    assert resolve_ingest_route(page_count, settings=settings) == expected
