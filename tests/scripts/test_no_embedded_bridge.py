# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Falsification matrix for Phase-3 no-embedded-bridge AST gate."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.check_no_embedded_bridge import (
    check_no_embedded_bridge,
    check_patrol_no_run_async,
)
from scripts.check_services_no_run_async import ServicesBridgeViolationError, check_services_file


def test_production_services_and_patrol_are_clean() -> None:
    assert check_no_embedded_bridge() == []


def test_patrol_tree_rejects_run_async(tmp_path: Path) -> None:
    (tmp_path / "result_cache.py").write_text(
        "from backend.repositories.async_bridge import run_async\n\ndef f():\n    run_async(x())\n",
        encoding="utf-8",
    )
    errors = check_patrol_no_run_async(patrol_root=tmp_path)
    assert len(errors) >= 1
    assert any("run_async" in item or "async_bridge" in item for item in errors)


def test_adapter_module_is_outside_forbidden_roots() -> None:
    """Regression: SyncAdapter lives under workflow/adapters, not services/patrol."""
    adapter = Path("backend/workflow/adapters/paper_service_sync.py")
    assert adapter.is_file()
    text = adapter.read_text(encoding="utf-8")
    assert "run_async" in text
    # Must not be scanned as a services/patrol violation.
    assert check_no_embedded_bridge() == []


def test_services_still_rejects_embedded_bridge(tmp_path: Path) -> None:
    path = tmp_path / "dirty.py"
    path.write_text(
        "from backend.repositories.async_bridge import run_async\n",
        encoding="utf-8",
    )
    with pytest.raises(ServicesBridgeViolationError):
        check_services_file(path, display_path="dirty.py")
