# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Tests for QA scale verification dependency."""

from __future__ import annotations

import pytest
from backend.api.qa_deps import verify_question_scale
from backend.rag.models import QuestionScale
from backend.schemas.qa_stream import QaStreamRequest
from fastapi import HTTPException


def test_verify_question_scale_returns_routable_scale() -> None:
    body = QaStreamRequest(question="这篇论文做了什么？")
    assert verify_question_scale("hss-001", body) == QuestionScale.SUMMARY


def test_verify_question_scale_raises_http_400_for_cross_paper() -> None:
    body = QaStreamRequest(question="How does this model compare to ResNet50?")
    with pytest.raises(HTTPException) as exc_info:
        verify_question_scale("hss-001", body)
    assert exc_info.value.status_code == 400
    assert "/patrol" in str(exc_info.value.detail)
