# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Bootstrap idempotency tests (SVC-BOOT-01 / D6 zero-pollution)."""

from __future__ import annotations

import pytest
from backend.config import get_settings
from backend.repositories.paper_repository import PaperRepository, get_paper_repository
from backend.services.paper_service import get_paper_service
from tests.helpers.persistence_testkit import (
    expected_demo_fixture_count,
    init_isolated_database,
    restart_paper_service,
    wipe_all_paper_rows,
)


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


@pytest.mark.asyncio
async def test_bootstrap_seed_without_singleton_reset_has_zero_pollution(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D6: DB-backed seed probe — no ``_bootstrapped`` flag; singleton reused across phases."""
    db_path = tmp_path / "bootstrap-zero-pollution.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("GRAPH_DATA_DIR", str(tmp_path / "graphs"))
    monkeypatch.setenv("SEED_DEMO_PAPERS", "true")
    get_settings.cache_clear()

    await init_isolated_database(db_path)
    from backend.repositories.pipeline_repository import get_pipeline_repository

    get_paper_repository.cache_clear()
    get_pipeline_repository.cache_clear()
    get_paper_service.cache_clear()
    service = get_paper_service()
    expected_count = expected_demo_fixture_count()

    await service.bootstrap()
    _, total_after_first = await service.list_papers()
    assert total_after_first == expected_count

    await service.bootstrap()
    _, total_after_second = await service.list_papers()
    assert total_after_second == expected_count

    await wipe_all_paper_rows()
    assert await PaperRepository().is_empty() is True

    await service.bootstrap()
    _, total_after_reseed = await service.list_papers()
    assert total_after_reseed == expected_count
