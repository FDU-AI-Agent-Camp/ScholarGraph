# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Falsification matrix for Phase-2 async hot-path await AST gate."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.check_async_hotpath_await import (
    HotpathAwaitViolationError,
    check_async_hotpath_await,
    check_hotpath_source,
)


def test_production_hotpaths_have_zero_violations() -> None:
    assert check_async_hotpath_await() == []


@pytest.mark.parametrize(
    "source",
    [
        "from backend.repositories.async_bridge import run_async\n",
        "def f():\n    run_async(x())\n",
        "async def f(svc):\n    svc.get_active_run_id('p')\n",
        "async def f(svc):\n    return svc.fail_pipeline('p', message='x')\n",
    ],
)
def test_forbidden_hotpath_patterns_raise(source: str) -> None:
    with pytest.raises(HotpathAwaitViolationError):
        check_hotpath_source(source, rel_path="probe.py")


def test_awaited_api_call_is_allowed() -> None:
    source = "async def f(svc):\n    await svc.get_active_run_id('p')\n    await svc.fail_pipeline('p', message='x')\n"
    check_hotpath_source(source, rel_path="probe.py")


def test_directory_matrix_reports_violations(tmp_path: Path) -> None:
    hot = tmp_path / "backend" / "rag"
    hot.mkdir(parents=True)
    (hot / "vector_store_replace.py").write_text(
        "async def f(svc):\n    svc.set_active_run_id('p', 'r')\n",
        encoding="utf-8",
    )
    # Other required paths missing → reported as missing; dirty file must also fail.
    errors = check_async_hotpath_await(repo_root=tmp_path)
    assert any("set_active_run_id" in item for item in errors)
