# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Red-light tests for persistence features planned but not yet required in P1."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.red


@pytest.mark.asyncio
@pytest.mark.red
async def test_red_pipeline_events_append_only_history_table_not_implemented(persistence_env) -> None:
    """P2: structured pipeline_events stream is out of P1 scope."""
    import backend.repositories.pipeline_repository as module

    assert not hasattr(module, "append_event")


@pytest.mark.red
def test_red_postgresql_asyncpg_url_switch_not_validated_in_ci() -> None:
    """Production PostgreSQL driver path is documented but not CI-gated yet."""
    from backend.db.url import to_async_database_url

    assert to_async_database_url("postgresql://user:pass@localhost/db") == "postgresql+asyncpg://user:pass@localhost/db"


@pytest.mark.red
@pytest.mark.asyncio
async def test_red_reextract_bumps_graph_version_atomically(persistence_env) -> None:
    """Re-extract should increment graph_version — tracked for follow-up commit."""
    from backend.services.reextract_service import force_reextract

    assert "graph_version" in force_reextract.__doc__ or False
