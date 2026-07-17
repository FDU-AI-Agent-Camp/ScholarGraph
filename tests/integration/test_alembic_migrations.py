# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Alembic upgrade/downgrade integration tests (D9 / RED-09)."""

from __future__ import annotations

import pytest
from backend.config import get_settings
from backend.db.migrations import (
    ALEMBIC_BASELINE_REVISION,
    ALEMBIC_HEAD_REVISION,
    downgrade_to,
    get_current_revision,
    upgrade_head,
)
from sqlalchemy import create_engine, text

from tests.helpers.persistence_testkit import reset_persistence_singletons

pytestmark = pytest.mark.integration


def run_alembic_cycle_assertions(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise upgrade head → downgrade baseline → upgrade head on a temp SQLite DB."""
    db_path = tmp_path / "alembic-cycle.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    reset_persistence_singletons()
    get_settings.cache_clear()

    upgrade_head()
    assert get_current_revision() == ALEMBIC_HEAD_REVISION

    downgrade_to(ALEMBIC_BASELINE_REVISION)
    assert get_current_revision() == ALEMBIC_BASELINE_REVISION

    sync_url = f"sqlite:///{db_path.as_posix()}"
    engine = create_engine(sync_url)
    with engine.connect() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(pipeline_runs)"))}
    assert "active_rag_run_id" not in columns
    assert "preview_graph" not in columns

    upgrade_head()
    assert get_current_revision() == ALEMBIC_HEAD_REVISION


@pytest.mark.integration
def test_alembic_upgrade_downgrade_cycle(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_alembic_cycle_assertions(tmp_path, monkeypatch)
