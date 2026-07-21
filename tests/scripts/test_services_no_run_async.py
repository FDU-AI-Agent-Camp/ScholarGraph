# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Falsification matrix for services async-bridge antifouling AST gate."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.check_services_no_run_async import (
    ServicesBridgeViolationError,
    check_services_file,
    check_services_no_run_async,
)


def test_clean_services_tree_has_no_run_async() -> None:
    assert check_services_no_run_async() == []


@pytest.mark.parametrize(
    "source",
    [
        "from backend.repositories.async_bridge import run_async\n",
        "from backend.repositories import run_async\n",
        "from backend.repositories import async_bridge\n",
        "import backend.repositories.async_bridge as bridge\n",
        "def f():\n    run_async(coro())\n",
        "def f(bridge):\n    bridge.run_async(coro())\n",
    ],
)
def test_forbidden_bridge_patterns_raise(tmp_path: Path, source: str) -> None:
    path = tmp_path / "dirty_service.py"
    path.write_text(source, encoding="utf-8")
    with pytest.raises(ServicesBridgeViolationError):
        check_services_file(path, display_path="dirty_service.py")


def test_sync_public_ssot_api_on_paper_service_raises(tmp_path: Path) -> None:
    path = tmp_path / "paper_service.py"
    path.write_text(
        "class PaperService:\n    def set_active_run_id(self, paper_id, run_id):\n        return None\n",
        encoding="utf-8",
    )
    with pytest.raises(ServicesBridgeViolationError, match="must be async def"):
        check_services_file(path, display_path="backend/services/paper_service.py")


def test_directory_scan_reports_violations(tmp_path: Path) -> None:
    (tmp_path / "ok.py").write_text("async def hello():\n    return 1\n", encoding="utf-8")
    (tmp_path / "bad.py").write_text(
        "from backend.repositories.async_bridge import run_async\n\ndef f():\n    run_async(x())\n",
        encoding="utf-8",
    )
    errors = check_services_no_run_async(services_root=tmp_path)
    assert len(errors) >= 1
    assert any("bad.py" in item for item in errors)
