# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for ORM ↔ Pydantic mappers."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.db.models import PaperRow, PipelineRunRow
from backend.repositories.mappers import paper_row_to_detail, pipeline_row_to_status
from backend.schemas.paper import FailedDuringStage, PaperStatus, PipelineStage
from backend.schemas.paradigm import Paradigm, ParadigmClassification


def test_paper_row_to_detail_parses_classification_json() -> None:
    now = datetime.now(UTC)
    row = PaperRow(
        paper_id="map-001",
        title="Mapper Test",
        paradigm=Paradigm.HSS.value,
        status=PaperStatus.READY.value,
        pdf_path="/tmp/map.pdf",
        classification={
            "paradigm": "HSS",
            "confidence": 0.88,
            "reason": "fixture",
        },
        created_at=now,
        updated_at=now,
    )
    detail = paper_row_to_detail(row)
    assert detail.classification == ParadigmClassification(
        paradigm=Paradigm.HSS,
        confidence=0.88,
        reason="fixture",
    )


def test_pipeline_row_to_status_maps_failed_during() -> None:
    now = datetime.now(UTC)
    paper = PaperRow(
        paper_id="map-002",
        title="Failed",
        status=PaperStatus.FAILED.value,
        pdf_path="/tmp/f.pdf",
        created_at=now,
        updated_at=now,
    )
    run = PipelineRunRow(
        paper_id="map-002",
        stage=PipelineStage.FAILED.value,
        percent=0,
        message="boom",
        error_code="PIPELINE_FAILED",
        failed_during=FailedDuringStage.EXTRACTING.value,
        created_at=now,
        updated_at=now,
        paper=paper,
    )
    status = pipeline_row_to_status(run)
    assert status.failed_during == FailedDuringStage.EXTRACTING
    assert status.error_code == "PIPELINE_FAILED"
