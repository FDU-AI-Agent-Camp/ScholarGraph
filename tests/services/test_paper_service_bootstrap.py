"""Bootstrap idempotency tests (SVC-BOOT-01)."""

from __future__ import annotations

import pytest
from backend.services.paper_service import get_paper_service
from tests.helpers.persistence_testkit import restart_paper_service


@pytest.mark.asyncio
async def test_bootstrap_twice_on_same_instance_is_idempotent(persistence_env) -> None:
    service = await restart_paper_service()
    items_first, total_first = await service.list_papers()
    await service.bootstrap()
    items_second, total_second = await service.list_papers()
    assert total_first == total_second == 0
    assert items_first == items_second == []


@pytest.mark.asyncio
async def test_bootstrap_with_seed_does_not_duplicate_fixture_rows(
    persistence_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEED_DEMO_PAPERS", "true")
    get_paper_service.cache_clear()
    service = await restart_paper_service()
    _, total_after_first = await service.list_papers()
    assert total_after_first >= 1

    await service.bootstrap()
    _, total_after_second = await service.list_papers()
    assert total_after_second == total_after_first
