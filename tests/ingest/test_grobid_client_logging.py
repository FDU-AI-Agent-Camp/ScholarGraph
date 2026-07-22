# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Boundary logging observability for GROBID ingest client."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from backend.ingest.grobid_client import check_grobid_isalive, fetch_grobid_tei

_LOGGER = "backend.ingest.grobid_client"


@pytest.mark.asyncio
async def test_grobid_health_check_failure_logs_structured_event(
    caplog: pytest.LogCaptureFixture,
) -> None:
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=ConnectionError("connection refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        caplog.at_level(logging.WARNING, logger=_LOGGER),
        patch("backend.ingest.grobid_client.httpx.AsyncClient", return_value=mock_client),
    ):
        alive = await check_grobid_isalive()

    assert alive is False
    records = [record for record in caplog.records if record.getMessage() == "grobid_health_check_failed"]
    assert len(records) == 1
    log_record = records[0]
    assert getattr(log_record, "url", "").endswith("/api/isalive")
    assert log_record.error == "connection refused"
    assert log_record.error_type == "ConnectionError"


@pytest.mark.asyncio
async def test_grobid_tei_extraction_failure_logs_structured_event(
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% minimal")

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=TimeoutError("grobid timed out"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        caplog.at_level(logging.WARNING, logger=_LOGGER),
        patch("backend.ingest.grobid_client.httpx.AsyncClient", return_value=mock_client),
    ):
        tei = await fetch_grobid_tei(pdf_path, paper_id="paper-grobid-001")

    assert tei is None
    records = [record for record in caplog.records if record.getMessage() == "grobid_tei_extraction_failed"]
    assert len(records) == 1
    log_record = records[0]
    assert log_record.paper_id == "paper-grobid-001"
    assert str(pdf_path.resolve()) in getattr(log_record, "pdf_path", "")
    assert log_record.error == "grobid timed out"
    assert log_record.error_type == "TimeoutError"
