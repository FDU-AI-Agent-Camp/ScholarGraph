# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Head merge and async refine robustness (edge cases, fallbacks)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from backend.config import Settings
from backend.ingest.head_candidates import HeadCandidate
from backend.ingest.head_merge import merge_with_rules
from backend.ingest.router import IngestRouteKind
from backend.ingest.tei_parser import parse_tei_to_head_candidate
from backend.services.head_refine_service import refine_head_async


def test_merge_with_rules_empty_candidates_produces_empty_head() -> None:
    merged = merge_with_rules(
        HeadCandidate(source="pymupdf"),
        None,
        is_short=True,
    )
    assert merged.title == ""
    assert merged.abstract == ""
    assert merged.sources["title"] == "empty"


def test_parse_tei_malformed_xml_raises() -> None:
    with pytest.raises(ET.ParseError):
        parse_tei_to_head_candidate("<not-valid-tei>")


@pytest.mark.asyncio
async def test_refine_head_tei_parse_failure_falls_back_to_snippets(structured_stem_pdf: Path) -> None:
    settings = Settings(
        _env_file=None,
        llm_mode="mock",
        ingest_route="auto",
        ingest_short_page_limit=0,
    )

    with (
        patch(
            "backend.services.head_refine_service.fetch_grobid_tei",
            new_callable=AsyncMock,
            return_value="<broken-tei>",
        ),
        patch(
            "backend.services.head_refine_service.parse_tei_to_head_candidate",
            side_effect=ValueError("invalid tei"),
        ),
        patch("backend.services.paper_service.get_paper_service"),
    ):
        result = await refine_head_async("paper-tei-fail", structured_stem_pdf, settings=settings)

    assert "tei_parse_failed" in result.warnings
    assert result.classifier_input.strip()


@pytest.mark.asyncio
async def test_refine_head_mineru_disabled_emits_warning(structured_stem_pdf: Path) -> None:
    settings = Settings(
        _env_file=None,
        llm_mode="mock",
        ingest_route="auto",
        ingest_short_page_limit=25,
        ingest_mineru_enabled=False,
    )

    with patch("backend.services.paper_service.get_paper_service"):
        result = await refine_head_async("paper-mineru-off", structured_stem_pdf, settings=settings)

    assert result.route == IngestRouteKind.SHORT
    assert "mineru_disabled" in result.warnings


@pytest.mark.asyncio
async def test_refine_head_pymupdf_only_skips_path_b(structured_stem_pdf: Path) -> None:
    settings = Settings(
        _env_file=None,
        llm_mode="mock",
        ingest_route="pymupdf_only",
    )

    with (
        patch(
            "backend.services.head_refine_service.run_mineru_pipeline",
        ) as mock_mineru,
        patch(
            "backend.services.head_refine_service.fetch_grobid_tei",
            new_callable=AsyncMock,
        ) as mock_grobid,
        patch("backend.services.paper_service.get_paper_service"),
    ):
        result = await refine_head_async("paper-pymupdf-only", structured_stem_pdf, settings=settings)

    assert result.route is None
    assert "route_pymupdf_only" in result.warnings
    mock_mineru.assert_not_called()
    mock_grobid.assert_not_awaited()


@pytest.mark.asyncio
async def test_refine_head_pymupdf_head_failure_still_merges(structured_stem_pdf: Path) -> None:
    settings = Settings(_env_file=None, llm_mode="mock", ingest_route="pymupdf_only")

    with (
        patch(
            "backend.services.head_refine_service.build_pymupdf_head_candidate",
            side_effect=ValueError("no text"),
        ),
        patch("backend.services.paper_service.get_paper_service"),
    ):
        result = await refine_head_async("paper-head-fail", structured_stem_pdf, settings=settings)

    assert "pymupdf_head_failed" in result.warnings
    assert isinstance(result.merged.title, str)


@pytest.mark.asyncio
async def test_pipeline_scheduler_refine_failure_does_not_fail_pipeline(tmp_path: Path) -> None:
    import asyncio

    from backend.services.paper_pipeline_scheduler import schedule_paper_pipeline

    pdf_path = tmp_path / "pipeline.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    with (
        patch(
            "backend.services.head_refine_service.refine_head_async",
            side_effect=RuntimeError("refine exploded"),
        ),
        patch(
            "backend.graph.workflow.run_paper_pipeline",
            new_callable=AsyncMock,
        ) as mock_pipeline,
    ):
        task = schedule_paper_pipeline("paper-sched", pdf_path)
        await task
        await asyncio.sleep(0)

    mock_pipeline.assert_awaited_once_with("paper-sched", pdf_path.resolve())
