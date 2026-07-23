# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""AST gate: forbid embedded ``run_async`` in core async domains (Phase-3).

Scan roots (zero-tolerance)::

    backend/services/**
    backend/patrol/**

Whitelist (outside scan roots — may call ``run_async``)::

    backend/repositories/async_bridge.py   # bridge implementation
    backend/events/bus.py                  # publish_sync / drain_sync
    backend/workflow/adapters/**           # PaperServiceSyncAdapter
    scripts/**                             # CLI / ops tools
    tests/**                               # fixtures and harnesses
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from scripts.check_services_no_run_async import (
    SERVICES_ROOT,
    ServicesBridgeViolationError,
    check_services_no_run_async,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PATROL_ROOT = REPO_ROOT / "backend" / "patrol"

_FORBIDDEN_ROOTS: tuple[Path, ...] = (SERVICES_ROOT, PATROL_ROOT)


def _iter_python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if path.is_file())


def _is_async_bridge_module(name: str) -> bool:
    return name == "async_bridge" or name.endswith(".async_bridge") or "async_bridge" in name.split(".")


def _check_patrol_file(path: Path, *, display_path: str) -> None:
    """Patrol modules: forbid run_async / async_bridge only (no SSOT async-def matrix)."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        raise ServicesBridgeViolationError(
            rel_path=display_path,
            lineno=exc.lineno or 0,
            detail="<syntax>",
        ) from exc

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if _is_async_bridge_module(name):
                    raise ServicesBridgeViolationError(
                        rel_path=display_path,
                        lineno=node.lineno,
                        detail=f"forbidden import of async_bridge ({name!r})",
                    )
                if alias.asname == "run_async" or name.endswith(".run_async"):
                    raise ServicesBridgeViolationError(
                        rel_path=display_path,
                        lineno=node.lineno,
                        detail="forbidden import of run_async",
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if _is_async_bridge_module(module):
                raise ServicesBridgeViolationError(
                    rel_path=display_path,
                    lineno=node.lineno,
                    detail=f"forbidden import from async_bridge ({module!r})",
                )
            imported = {alias.name for alias in node.names}
            if "run_async" in imported or "async_bridge" in imported:
                raise ServicesBridgeViolationError(
                    rel_path=display_path,
                    lineno=node.lineno,
                    detail="forbidden import of run_async / async_bridge",
                )
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "run_async":
                raise ServicesBridgeViolationError(
                    rel_path=display_path,
                    lineno=node.lineno,
                    detail="forbidden call to run_async(...)",
                )
            if isinstance(func, ast.Attribute) and func.attr == "run_async":
                raise ServicesBridgeViolationError(
                    rel_path=display_path,
                    lineno=node.lineno,
                    detail="forbidden call to *.run_async(...)",
                )


def check_patrol_no_run_async(*, patrol_root: Path = PATROL_ROOT) -> list[str]:
    errors: list[str] = []
    if not patrol_root.is_dir():
        return [f"{patrol_root}: missing directory"]
    for path in _iter_python_files(patrol_root):
        try:
            if patrol_root == PATROL_ROOT:
                display = path.relative_to(REPO_ROOT).as_posix()
            else:
                display = path.relative_to(patrol_root).as_posix()
            _check_patrol_file(path, display_path=display)
        except ServicesBridgeViolationError as exc:
            errors.append(str(exc))
    return errors


def check_no_embedded_bridge(
    *,
    services_root: Path = SERVICES_ROOT,
    patrol_root: Path = PATROL_ROOT,
) -> list[str]:
    """Return violation strings for services (SSOT) + patrol (bridge-only)."""
    errors = check_services_no_run_async(services_root=services_root)
    errors.extend(check_patrol_no_run_async(patrol_root=patrol_root))
    return errors


def main() -> int:
    errors = check_no_embedded_bridge()
    if errors:
        print(
            f"{len(errors)} violation(s) found in backend/services/ + backend/patrol/:",
            file=sys.stderr,
        )
        for line in errors:
            print(f"  {line}", file=sys.stderr)
        return 1
    scanned = " + ".join(str(root.relative_to(REPO_ROOT).as_posix()) for root in _FORBIDDEN_ROOTS)
    print(f"0 violations found in {scanned}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
