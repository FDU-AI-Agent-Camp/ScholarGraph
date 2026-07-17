# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""F.2.3 unit: PaperDetail / PaperStatusData extract_warnings schema (X13, X17)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE
from backend.schemas.paper import PaperDetail, PaperStatus, PaperStatusData

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "docs" / "api" / "fixtures"


def test_x13_paper_status_data_accepts_extract_warnings() -> None:
    status = PaperStatusData(
        paper_id="unit-f23-status",
        status=PaperStatus.READY,
        percent=100,
        stage=None,
        message="建图完成",
        updated_at=datetime.now(UTC),
        extract_warnings=[EXTRACT_HEURISTIC_FALLBACK_CODE],
    )
    assert status.extract_warnings == [EXTRACT_HEURISTIC_FALLBACK_CODE]


def test_x17_paper_detail_defaults_extract_warnings_to_empty_list() -> None:
    now = datetime.now(UTC)
    detail = PaperDetail(
        paper_id="unit-f23-detail",
        title="t",
        status=PaperStatus.READY,
        created_at=now,
        updated_at=now,
    )
    assert detail.extract_warnings == []


def test_x17_paper_detail_accepts_extract_warnings_field() -> None:
    now = datetime.now(UTC)
    detail = PaperDetail(
        paper_id="unit-f23-detail-warn",
        title="t",
        status=PaperStatus.READY,
        created_at=now,
        updated_at=now,
        extract_warnings=[EXTRACT_HEURISTIC_FALLBACK_CODE],
    )
    assert detail.extract_warnings == [EXTRACT_HEURISTIC_FALLBACK_CODE]


def test_x20_ready_fallback_fixtures_validate() -> None:
    status_payload = json.loads((FIXTURES_DIR / "paper-status-ready-fallback.json").read_text(encoding="utf-8"))
    detail_payload = json.loads((FIXTURES_DIR / "paper-detail-ready-fallback.json").read_text(encoding="utf-8"))

    status = PaperStatusData.model_validate(status_payload["data"])
    detail = PaperDetail.model_validate(detail_payload["data"])

    assert status.extract_warnings == [EXTRACT_HEURISTIC_FALLBACK_CODE]
    assert detail.extract_warnings == [EXTRACT_HEURISTIC_FALLBACK_CODE]


@pytest.mark.parametrize(
    "filename",
    ("paper-detail-ready.json", "paper-detail-ready-fallback.json"),
)
def test_x20_paper_detail_fixtures_include_extract_warnings(filename: str) -> None:
    payload = json.loads((FIXTURES_DIR / filename).read_text(encoding="utf-8"))
    assert "extract_warnings" in payload["data"]
