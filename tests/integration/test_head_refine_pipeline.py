"""Phase C: classify consumes dual(rules) refined head after wait (P4 / T2)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from backend.graph.workflow import run_paper_pipeline
from backend.schemas.ingest_head import IngestHead
from backend.services.head_refine_wait import HEAD_REFINE_TIMEOUT_WARNING
from backend.services.paper_service import get_paper_service

from tests.conftest import mock_pipeline_node_services

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_pipeline_classify_uses_refined_classifier_input(integration_paper: tuple[str, Path]) -> None:
    paper_id, pdf_path = integration_paper
    refined_text = "Title: MinerU Refined\nAbstract: Better abstract"

    async def _instant_refined(_pid: str, _path: Path, fallback: str, **_: object) -> tuple[str, list[str]]:
        get_paper_service().apply_head_refine(
            paper_id,
            merged=IngestHead(title="MinerU Refined", abstract="Better abstract"),
            classifier_input=refined_text,
            warnings=[],
        )
        return refined_text, []

    with mock_pipeline_node_services(paper_id) as mocks:
        with (
            patch("backend.graph.nodes.wait_for_refined_classifier_input", side_effect=_instant_refined),
            patch("backend.graph.nodes.ensure_head_refine_scheduled"),
        ):
            final = await run_paper_pipeline(paper_id, pdf_path)

    classify_arg = mocks["agent"].classify_paradigm.await_args.args[0]
    assert classify_arg == refined_text
    assert classify_arg != "classifier-input"
    assert final.get("failed") is not True


@pytest.mark.asyncio
async def test_pipeline_extract_uses_ingest_full_text_not_refined_head(
    integration_paper: tuple[str, Path],
) -> None:
    """P5: full_text stays PyMuPDF; only classifier_input is replaced."""
    paper_id, pdf_path = integration_paper
    ingest_full_text = "PYMUPDF-FULL-TEXT-BODY"
    refined_text = "Title: Refined Only For Classify"

    async def _instant_refined(_pid: str, _path: Path, fallback: str, **_: object) -> tuple[str, list[str]]:
        return refined_text, []

    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["ingest"].ingest = AsyncMock(
            return_value={
                "paper_id": paper_id,
                "full_text": ingest_full_text,
                "classifier_input": "snippet-fallback",
            },
        )
        with (
            patch("backend.graph.nodes.wait_for_refined_classifier_input", side_effect=_instant_refined),
            patch("backend.graph.nodes.ensure_head_refine_scheduled"),
        ):
            await run_paper_pipeline(paper_id, pdf_path)

    extract_args = mocks["agent"].extract_graph.await_args
    assert extract_args is not None
    assert extract_args.args[0] == ingest_full_text


@pytest.mark.asyncio
async def test_pipeline_classify_falls_back_on_head_refine_timeout(
    integration_paper: tuple[str, Path],
) -> None:
    paper_id, pdf_path = integration_paper
    snippet_input = "SNIPPET-CLASSIFIER-INPUT"

    async def _timeout(_pid: str, _path: Path, fallback: str, **_: object) -> tuple[str, list[str]]:
        return fallback, [HEAD_REFINE_TIMEOUT_WARNING]

    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["ingest"].ingest = AsyncMock(
            return_value={
                "paper_id": paper_id,
                "full_text": "body",
                "classifier_input": snippet_input,
            },
        )
        with (
            patch("backend.graph.nodes.wait_for_refined_classifier_input", side_effect=_timeout),
            patch("backend.graph.nodes.ensure_head_refine_scheduled"),
        ):
            final = await run_paper_pipeline(paper_id, pdf_path)

    classify_arg = mocks["agent"].classify_paradigm.await_args.args[0]
    assert classify_arg == snippet_input
    assert final.get("head_refine_warnings") == [HEAD_REFINE_TIMEOUT_WARNING]
