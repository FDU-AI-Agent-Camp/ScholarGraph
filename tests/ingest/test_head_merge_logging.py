# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Boundary logging observability for head merge LLM fallback."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.config import Settings
from backend.ingest.head_candidates import HeadCandidate
from backend.ingest.head_merge import merge_with_llm

_LOGGER = "backend.ingest.head_merge"


@pytest.mark.asyncio
async def test_head_merge_llm_failure_logs_structured_event(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = Settings(_env_file=None, llm_mode="live", ingest_head_llm_enabled=True)
    snippets = HeadCandidate(title="Sample Title", source="pymupdf")
    mock_chat = MagicMock()
    mock_structured = MagicMock()
    mock_structured.ainvoke = AsyncMock(side_effect=RuntimeError("structured output failed"))
    mock_chat.with_structured_output.return_value = mock_structured
    mock_client = MagicMock()
    mock_client.chat = mock_chat
    mock_client.fallback_chat = None

    with (
        caplog.at_level(logging.WARNING, logger=_LOGGER),
        patch("backend.ingest.head_merge.get_llm_client", return_value=mock_client),
    ):
        merged = await merge_with_llm(
            snippets,
            None,
            is_short=True,
            settings=settings,
            paper_id="paper-head-001",
        )

    assert merged.title == "Sample Title"
    records = [record for record in caplog.records if record.getMessage() == "head_merge_failed"]
    assert len(records) == 1
    log_record = records[0]
    assert log_record.paper_id == "paper-head-001"
    assert log_record.phase == "llm_invoke"
    assert "structured output failed" in getattr(log_record, "error", "")
    assert log_record.error_type == "RuntimeError"
