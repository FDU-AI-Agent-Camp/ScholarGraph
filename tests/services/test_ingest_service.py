"""Functional and error-mapping tests for IngestService."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from backend.services.errors import ServiceError
from backend.services.ingest_service import IngestService, get_ingest_service


async def test_ingest_success_returns_be_payload(tmp_path: Path) -> None:
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    expected = {
        "paper_id": "p-1",
        "full_text": "全文",
        "classifier_input": "摘要片段",
    }
    service = IngestService()
    with patch("backend.services.ingest_service.ingest_pdf", new_callable=AsyncMock) as raw:
        raw.return_value = expected
        result = await service.ingest(pdf, paper_id="p-1")

    raw.assert_awaited_once_with(pdf, paper_id="p-1")
    assert result == expected


@pytest.mark.parametrize(
    ("exc", "expected_code"),
    [
        (NotImplementedError("BE-1"), "PIPELINE_FAILED"),
        (ValueError("corrupt"), "INGEST_FAILED"),
        (OSError("io"), "INGEST_FAILED"),
    ],
)
async def test_ingest_maps_exceptions_to_service_error(
    tmp_path: Path,
    exc: Exception,
    expected_code: str,
) -> None:
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF")
    service = IngestService()
    with patch("backend.services.ingest_service.ingest_pdf", new_callable=AsyncMock) as raw:
        raw.side_effect = exc
        with pytest.raises(ServiceError) as err:
            await service.ingest(pdf, paper_id="p-1")
    assert err.value.code == expected_code
    assert err.value.message


def test_get_ingest_service_returns_singleton() -> None:
    get_ingest_service.cache_clear()
    assert get_ingest_service() is get_ingest_service()
    get_ingest_service.cache_clear()
