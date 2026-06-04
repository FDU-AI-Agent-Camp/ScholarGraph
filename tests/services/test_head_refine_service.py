"""Async head refine orchestration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from backend.config import Settings
from backend.ingest.head_candidates import HeadCandidate
from backend.ingest.router import IngestRouteKind
from backend.schemas.ingest_head import IngestHead
from backend.services.head_refine_service import refine_head_async


@pytest.mark.asyncio
async def test_refine_head_async_long_pdf_uses_grobid_and_rules(tmp_path: Path) -> None:
    pdf_path = tmp_path / "long.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    settings = Settings(
        _env_file=None,
        llm_mode="mock",
        ingest_route="auto",
        ingest_short_page_limit=0,
    )
    grobid_candidate = HeadCandidate(
        title="GROBID Title",
        abstract="From TEI",
        source="grobid",
    )
    merged = IngestHead(
        title="GROBID Title",
        abstract="From TEI",
        sources={"title": "grobid", "abstract": "grobid"},
    )

    with (
        patch("backend.services.head_refine_service.get_pdf_page_count", return_value=30),
        patch(
            "backend.services.head_refine_service.build_pymupdf_head_candidate",
            return_value=HeadCandidate(title="Snippet", source="pymupdf"),
        ),
        patch(
            "backend.services.head_refine_service.fetch_grobid_tei",
            new_callable=AsyncMock,
            return_value="<TEI/>",
        ),
        patch(
            "backend.services.head_refine_service.parse_tei_to_head_candidate",
            return_value=grobid_candidate,
        ),
        patch(
            "backend.services.head_refine_service.get_head_merge_service",
        ) as mock_merge_service,
        patch("backend.services.paper_service.get_paper_service") as mock_paper_service,
    ):
        mock_merge_service.return_value.merge = AsyncMock(return_value=merged)
        result = await refine_head_async("paper-1", pdf_path, settings=settings)

    assert result.route == IngestRouteKind.LONG
    assert result.classifier_input.startswith("Title: GROBID Title")
    mock_paper_service.return_value.apply_head_refine.assert_called_once()


@pytest.mark.asyncio
async def test_refine_head_async_never_raises_on_grobid_failure(tmp_path: Path) -> None:
    pdf_path = tmp_path / "short.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    settings = Settings(
        _env_file=None,
        llm_mode="mock",
        ingest_route="auto",
        ingest_short_page_limit=25,
        ingest_mineru_enabled=False,
    )

    with (
        patch("backend.services.head_refine_service.get_pdf_page_count", return_value=30),
        patch(
            "backend.services.head_refine_service.build_pymupdf_head_candidate",
            return_value=HeadCandidate(title="Snippet", source="pymupdf"),
        ),
        patch(
            "backend.services.head_refine_service.fetch_grobid_tei",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("backend.services.paper_service.get_paper_service"),
    ):
        result = await refine_head_async("paper-2", pdf_path, settings=settings)

    assert "grobid_unavailable" in result.warnings
    assert "Snippet" in result.classifier_input or result.merged.title == "Snippet"
