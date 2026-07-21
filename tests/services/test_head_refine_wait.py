# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for head refine wait polling (Phase C / P4)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest
from backend.config import Settings
from backend.schemas.ingest_head import IngestHead
from backend.services.head_refine_wait import (
    HEAD_REFINE_TIMEOUT_WARNING,
    resolve_head_refine_timeout_seconds,
    wait_for_refined_classifier_input,
)
from backend.services.paper_service import get_paper_service


def test_resolve_head_refine_timeout_short_uses_mineru_budget() -> None:
    settings = Settings(_env_file=None, ingest_mineru_timeout_seconds=600, grobid_timeout_seconds=300)
    assert resolve_head_refine_timeout_seconds(10, settings=settings) == 600.0


def test_resolve_head_refine_timeout_long_uses_grobid_budget() -> None:
    settings = Settings(_env_file=None, ingest_mineru_timeout_seconds=600, grobid_timeout_seconds=300)
    assert resolve_head_refine_timeout_seconds(30, settings=settings) == 300.0


def test_resolve_head_refine_timeout_pymupdf_only_is_brief() -> None:
    settings = Settings(_env_file=None, ingest_route="pymupdf_only")
    assert resolve_head_refine_timeout_seconds(30, settings=settings) == 30.0


@pytest.mark.asyncio
async def test_wait_returns_refined_input_when_ready(persistence_env, tmp_path: Path) -> None:
    from backend.schemas.paper import PaperStatus
    from tests.helpers.persistence_testkit import register_test_paper

    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% mock content")
    paper_id = "wait-ready"
    await register_test_paper(paper_id, status=PaperStatus.PROCESSING)

    async def _apply_refined() -> None:
        await asyncio.sleep(0.05)
        await get_paper_service().apply_head_refine(
            paper_id,
            merged=IngestHead(title="Refined Title"),
            classifier_input="Title: Refined Title",
        )

    task = asyncio.create_task(_apply_refined())
    with patch("backend.services.head_refine_wait.get_pdf_page_count", return_value=10):
        refined, warnings = await wait_for_refined_classifier_input(
            paper_id,
            pdf_path,
            "fallback",
            settings=Settings(_env_file=None, ingest_route="pymupdf_only"),
        )
    await task

    assert refined == "Title: Refined Title"
    assert warnings == []


@pytest.mark.asyncio
async def test_wait_timeout_falls_back_to_snippets(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% mock content")

    with (
        patch("backend.services.head_refine_wait.get_pdf_page_count", return_value=10),
        patch("backend.services.head_refine_wait.HEAD_REFINE_POLL_SECONDS", 0.01),
    ):
        refined, warnings = await wait_for_refined_classifier_input(
            "wait-timeout",
            pdf_path,
            "SNIPPET-FALLBACK",
            settings=Settings(_env_file=None, ingest_route="pymupdf_only"),
        )

    assert refined == "SNIPPET-FALLBACK"
    assert HEAD_REFINE_TIMEOUT_WARNING in warnings


@pytest.mark.asyncio
async def test_wait_returns_path_b_warnings_from_paper_service(
    persistence_env,
    tmp_path: Path,
) -> None:
    from backend.schemas.paper import PaperStatus
    from tests.helpers.persistence_testkit import register_test_paper

    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% mock content")
    paper_id = "wait-warnings"
    await register_test_paper(paper_id, status=PaperStatus.PROCESSING)

    await get_paper_service().apply_head_refine(
        paper_id,
        merged=IngestHead(title="T"),
        classifier_input="Title: T",
        warnings=["grobid_unavailable", "route_pymupdf_only"],
    )

    with patch("backend.services.head_refine_wait.get_pdf_page_count", return_value=30):
        refined, warnings = await wait_for_refined_classifier_input(
            paper_id,
            pdf_path,
            "fallback",
            settings=Settings(_env_file=None, ingest_route="auto"),
        )

    assert refined == "Title: T"
    assert warnings == ["grobid_unavailable", "route_pymupdf_only"]
