# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Boundary logging observability for MinerU ingest path."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest
from backend.config import Settings
from backend.ingest.mineru_backend import resolve_mineru_lang

_LOGGER = "backend.ingest.mineru_backend"


def test_mineru_lang_detection_failure_logs_structured_event(
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    invalid_pdf = tmp_path / "corrupted.pdf"
    invalid_pdf.write_bytes(b"not a pdf")
    settings = Settings(_env_file=None, ingest_mineru_lang="")

    with (
        caplog.at_level(logging.WARNING, logger=_LOGGER),
        patch(
            "backend.ingest.pdf.extract_pdf_text",
            side_effect=RuntimeError("pdf parse failed"),
        ),
    ):
        lang = resolve_mineru_lang(invalid_pdf, settings=settings)

    assert lang == "en"
    records = [record for record in caplog.records if record.getMessage() == "mineru_lang_detection_failed"]
    assert len(records) == 1
    log_record = records[0]
    assert log_record.pdf_path == str(invalid_pdf)
    assert log_record.default_lang == "en"
    assert log_record.error == "pdf parse failed"
    assert log_record.error_type == "RuntimeError"
