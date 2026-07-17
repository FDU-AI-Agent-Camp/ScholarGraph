# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Dual-route ingest functional tests: page threshold and path-B dispatch."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from backend.config import Settings
from backend.ingest.head_candidates import HeadCandidate
from backend.ingest.pdf import CLASSIFIER_HEAD_PAGE_LIMIT, ingest_pdf
from backend.ingest.router import (
    IngestRouteKind,
    get_pdf_page_count,
    resolve_ingest_route,
)
from backend.services.head_refine_service import refine_head_async


def test_classifier_head_limit_matches_ingest_default() -> None:
    settings = Settings(_env_file=None)
    assert settings.ingest_short_page_limit == CLASSIFIER_HEAD_PAGE_LIMIT == 25


def test_pdf_25_pages_boundary_is_short_route(pdf_25_pages: Path) -> None:
    settings = Settings(_env_file=None, ingest_route="auto", ingest_short_page_limit=25)
    page_count = get_pdf_page_count(pdf_25_pages)
    assert page_count == 25
    assert resolve_ingest_route(page_count, settings=settings) == IngestRouteKind.SHORT


def test_pdf_26_pages_boundary_is_long_route(pdf_26_pages: Path) -> None:
    settings = Settings(_env_file=None, ingest_route="auto", ingest_short_page_limit=25)
    page_count = get_pdf_page_count(pdf_26_pages)
    assert page_count == 26
    assert resolve_ingest_route(page_count, settings=settings) == IngestRouteKind.LONG


def test_custom_ingest_short_page_limit_overrides_default() -> None:
    settings = Settings(_env_file=None, ingest_route="auto", ingest_short_page_limit=10)
    assert resolve_ingest_route(10, settings=settings) == IngestRouteKind.SHORT
    assert resolve_ingest_route(11, settings=settings) == IngestRouteKind.LONG


@pytest.mark.asyncio
async def test_ingest_pdf_sync_never_calls_mineru_or_grobid(structured_stem_pdf: Path) -> None:
    with (
        patch("backend.ingest.mineru_backend.run_mineru_pipeline") as mock_mineru,
        patch("backend.ingest.grobid_client.fetch_grobid_tei", new_callable=AsyncMock) as mock_grobid,
    ):
        result = await ingest_pdf(structured_stem_pdf, paper_id="sync-only")

    mock_mineru.assert_not_called()
    mock_grobid.assert_not_called()
    assert result["full_text"].strip()
    assert result["classifier_input"].strip()


@pytest.mark.asyncio
async def test_refine_head_25_pages_dispatches_mineru_not_grobid(pdf_25_pages: Path) -> None:
    settings = Settings(
        _env_file=None,
        llm_mode="mock",
        ingest_route="auto",
        ingest_short_page_limit=25,
        ingest_mineru_enabled=True,
    )
    mineru_candidate = HeadCandidate(title="MinerU Title", source="mineru")

    with (
        patch(
            "backend.services.head_refine_service.run_mineru_pipeline",
            return_value=mineru_candidate,
        ) as mock_mineru,
        patch(
            "backend.services.head_refine_service.fetch_grobid_tei",
            new_callable=AsyncMock,
        ) as mock_grobid,
        patch("backend.services.paper_service.get_paper_service"),
    ):
        result = await refine_head_async("paper-short", pdf_25_pages, settings=settings)

    assert result.page_count == 25
    assert result.route == IngestRouteKind.SHORT
    mock_mineru.assert_called_once()
    mock_grobid.assert_not_called()
    assert "MinerU Title" in result.classifier_input


@pytest.mark.asyncio
async def test_refine_head_26_pages_dispatches_grobid_not_mineru(pdf_26_pages: Path) -> None:
    settings = Settings(
        _env_file=None,
        llm_mode="mock",
        ingest_route="auto",
        ingest_short_page_limit=25,
    )
    tei_fixture = (Path(__file__).parent / "fixtures" / "grobid_sample.tei.xml").read_text(
        encoding="utf-8",
    )
    grobid_candidate = HeadCandidate(title="Sample GROBID Title", source="grobid")

    with (
        patch(
            "backend.services.head_refine_service.run_mineru_pipeline",
        ) as mock_mineru,
        patch(
            "backend.services.head_refine_service.fetch_grobid_tei",
            new_callable=AsyncMock,
            return_value=tei_fixture,
        ) as mock_grobid,
        patch(
            "backend.services.head_refine_service.parse_tei_to_head_candidate",
            return_value=grobid_candidate,
        ),
        patch("backend.services.paper_service.get_paper_service"),
    ):
        result = await refine_head_async("paper-long", pdf_26_pages, settings=settings)

    assert result.page_count == 26
    assert result.route == IngestRouteKind.LONG
    mock_grobid.assert_awaited_once()
    mock_mineru.assert_not_called()
    assert "Sample GROBID Title" in result.classifier_input
