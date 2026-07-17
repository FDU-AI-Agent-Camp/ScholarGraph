# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Test-only SQLite schema bootstrap via ``create_all`` (never used in production)."""

from __future__ import annotations

import backend.db.models  # noqa: F401 — register ORM tables on Base.metadata
from backend.db.base import Base
from sqlalchemy.ext.asyncio import AsyncEngine


async def create_all_tables(engine: AsyncEngine) -> None:
    """Create ORM tables for isolated pytest databases."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
