# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for SEED_DEMO_PAPERS conditional fixture loading."""

from __future__ import annotations

import pytest
from backend.services.paper_service import get_paper_service

from tests.helpers.persistence_testkit import restart_paper_service


@pytest.mark.integration
@pytest.mark.asyncio
async def test_empty_db_without_seed_returns_empty_list(persistence_env) -> None:
    service = await restart_paper_service()
    items, total = await service.list_papers()
    assert total == 0
    assert items == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_seed_demo_papers_loads_fixture_items_when_db_empty(
    persistence_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEED_DEMO_PAPERS", "true")
    get_paper_service.cache_clear()
    service = await restart_paper_service()
    items, total = await service.list_papers()
    assert total >= 1
    paper_ids = {item.paper_id for item in items}
    assert "hss-001" in paper_ids


@pytest.mark.integration
@pytest.mark.asyncio
async def test_seed_demo_papers_skipped_when_db_not_empty(
    persistence_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.repositories.paper_repository import PaperRepository

    repo = PaperRepository()
    await repo.create("real-user-upload", "User Upload", "/tmp/real.pdf")

    monkeypatch.setenv("SEED_DEMO_PAPERS", "true")
    get_paper_service.cache_clear()
    service = await restart_paper_service()
    items, total = await service.list_papers()
    assert total == 1
    assert items[0].paper_id == "real-user-upload"
