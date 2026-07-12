"""Unit tests for sync/async repository bridge (U-BRG-01/02)."""

from __future__ import annotations

import asyncio

import pytest
from backend.repositories.async_bridge import run_async


@pytest.mark.asyncio
async def test_run_async_from_running_loop_returns_value() -> None:
    async def compute() -> int:
        await asyncio.sleep(0)
        return 42

    assert run_async(compute()) == 42


def test_run_async_without_running_loop_returns_value() -> None:
    async def compute() -> str:
        return "ok"

    assert run_async(compute()) == "ok"
