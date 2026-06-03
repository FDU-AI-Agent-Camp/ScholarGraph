"""Ingest error mapping and message reporting (BE-1)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from backend.graph import nodes
from backend.graph.state import WorkflowState, initial_workflow_state
from backend.ingest.pdf import extract_pdf_text
from backend.schemas.paper import PipelineStage
from backend.services.errors import ServiceError
from backend.services.ingest_service import IngestService, get_ingest_service
from tests.ingest.conftest import register_pending_paper, write_empty_page_pdf, write_zero_page_pdf


@pytest.mark.parametrize(
    ("factory", "expected_substring"),
    [
        (write_zero_page_pdf, "PDF 无页面"),
        (write_empty_page_pdf, "PDF 未提取到文本"),
    ],
)
def test_extract_pdf_text_error_messages_include_path(
    tmp_path: Path,
    factory,
    expected_substring: str,
) -> None:
    pdf_path = factory(tmp_path / "bad.pdf")

    with pytest.raises(ValueError, match=expected_substring) as exc_info:
        extract_pdf_text(pdf_path)

    assert str(pdf_path.resolve()) in str(exc_info.value)


@pytest.mark.parametrize(
    ("factory", "expected_message_part"),
    [
        (write_zero_page_pdf, "PDF 无页面"),
        (write_empty_page_pdf, "PDF 未提取到文本"),
    ],
)
async def test_ingest_service_maps_pdf_errors_to_ingest_failed(
    tmp_path: Path,
    factory,
    expected_message_part: str,
) -> None:
    pdf_path = factory(tmp_path / "bad.pdf")
    service = IngestService()

    with pytest.raises(ServiceError) as exc_info:
        await service.ingest(pdf_path, paper_id="bad-doc")

    assert exc_info.value.code == "INGEST_FAILED"
    assert "PDF 解析失败" in exc_info.value.message
    assert expected_message_part in exc_info.value.message


async def test_ingest_service_maps_missing_file_to_ingest_failed(tmp_path: Path) -> None:
    missing = tmp_path / "missing.pdf"
    service = IngestService()

    with pytest.raises(ServiceError) as exc_info:
        await service.ingest(missing, paper_id="missing-doc")

    assert exc_info.value.code == "INGEST_FAILED"
    assert "PDF 解析失败" in exc_info.value.message
    assert "PDF 不存在" in exc_info.value.message


async def test_ingest_node_reports_ingest_failed_from_real_corrupt_pdf(
    tmp_path: Path,
) -> None:
    paper_id = "ingest-node-corrupt"
    pdf_path = tmp_path / f"{paper_id}.pdf"
    pdf_path.write_bytes(b"not-a-valid-pdf")
    register_pending_paper(paper_id)
    state: WorkflowState = initial_workflow_state(paper_id=paper_id, pdf_path=str(pdf_path))

    get_ingest_service.cache_clear()
    try:
        out = await nodes.ingest_node(state)
    finally:
        get_ingest_service.cache_clear()

    assert out["failed"] is True
    assert out["error_code"] == "INGEST_FAILED"
    assert out["stage"] == PipelineStage.INGESTING
    assert "PDF 解析失败" in (out["error_message"] or "")


async def test_ingest_node_reports_blank_pdf_message(tmp_path: Path) -> None:
    paper_id = "ingest-node-blank"
    pdf_path = write_empty_page_pdf(tmp_path / f"{paper_id}.pdf")
    register_pending_paper(paper_id)
    state: WorkflowState = initial_workflow_state(paper_id=paper_id, pdf_path=str(pdf_path))

    get_ingest_service.cache_clear()
    try:
        out = await nodes.ingest_node(state)
    finally:
        get_ingest_service.cache_clear()

    assert out["failed"] is True
    assert out["error_code"] == "INGEST_FAILED"
    assert "PDF 未提取到文本" in (out["error_message"] or "")


async def test_ingest_service_success_with_real_structured_pdf(structured_stem_pdf: Path) -> None:
    service = IngestService()

    result = await service.ingest(structured_stem_pdf, paper_id="structured-stem")

    assert result["paper_id"] == "structured-stem"
    assert "machine learning" in result["full_text"]
    assert "Abstract:" in result["classifier_input"]
    assert "Keywords:" in result["classifier_input"]


async def test_ingest_node_success_with_real_pdf_no_mock(
    structured_stem_pdf: Path,
) -> None:
    paper_id = "ingest-node-real"
    register_pending_paper(paper_id)
    state: WorkflowState = initial_workflow_state(
        paper_id=paper_id,
        pdf_path=str(structured_stem_pdf),
    )

    get_ingest_service.cache_clear()
    try:
        out = await nodes.ingest_node(state)
    finally:
        get_ingest_service.cache_clear()

    assert out.get("failed") is not True
    assert out["full_text"].strip()
    assert "classifier_input" in out
    assert "machine learning" in out["classifier_input"]


async def test_ingest_pdf_not_implemented_still_maps_pipeline_failed(tmp_path: Path) -> None:
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    service = IngestService()

    with patch("backend.services.ingest_service.ingest_pdf", side_effect=NotImplementedError("BE-1 pending")):
        with pytest.raises(ServiceError) as exc_info:
            await service.ingest(pdf_path, paper_id="p-1")

    assert exc_info.value.code == "PIPELINE_FAILED"
    assert "BE-1 pending" in exc_info.value.message
