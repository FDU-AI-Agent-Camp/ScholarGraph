# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Integration tests: head/classify/extract warnings survive service restart (INT-HEAD-01)."""

from __future__ import annotations

import pytest
from backend.services.paper_warning_service import WarningType, get_paper_warning_service

from tests.helpers.persistence_testkit import register_test_paper, restart_paper_service


@pytest.mark.integration
@pytest.mark.asyncio
async def test_head_refine_warnings_persist_across_restart(persistence_env) -> None:
    paper_id = "warn-head-001"
    await register_test_paper(paper_id)
    service = await restart_paper_service()
    await get_paper_warning_service().record(paper_id, WarningType.HEAD_REFINE, ["head_refine_timeout"])

    service = await restart_paper_service()
    assert await get_paper_warning_service().get(paper_id, WarningType.HEAD_REFINE) == ["head_refine_timeout"]
    status = await service.get_status(paper_id)
    assert status.head_refine_warnings == ["head_refine_timeout"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_all_warning_categories_persist_across_restart(persistence_env) -> None:
    paper_id = "warn-all-001"
    await register_test_paper(paper_id)
    service = await restart_paper_service()
    await get_paper_warning_service().record(paper_id, WarningType.HEAD_REFINE, ["head_refine_timeout"])
    await get_paper_warning_service().record(paper_id, WarningType.CLASSIFY, ["classifier_heuristic_fallback"])
    await get_paper_warning_service().record(paper_id, WarningType.EXTRACT, ["extract_heuristic_fallback"])

    service = await restart_paper_service()
    detail = await service.get_paper(paper_id)
    assert detail.classify_warnings == ["classifier_heuristic_fallback"]
    assert detail.extract_warnings == ["extract_heuristic_fallback"]

    status = await service.get_status(paper_id)
    assert status.head_refine_warnings == ["head_refine_timeout"]
    assert status.classify_warnings == ["classifier_heuristic_fallback"]
    assert status.extract_warnings == ["extract_heuristic_fallback"]
